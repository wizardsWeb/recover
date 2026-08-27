"""The nine-step agent loop.

``run_agent_loop`` is the whole agent. Everything else in ``app.agent`` is a
step it calls, and every step obeys the same contract: take the case, return a
Pydantic result, touch only the tables you own. The orchestrator is the only
place that knows the order, writes the case's state transitions, and decides
when a pass ends early.

The order is not arbitrary:

    detect → diagnose → uplift → decide → guardrail → execute → listen → learn → audit

*Diagnose before decide* because the action should follow from the cause.
*Uplift before decide* because the cheapest action is the one you establish you
do not need. *Guardrail after decide and before execute* because the veto has to
see the concrete action, not the intent — and because a blocked decision is
still a decision worth recording. *Learn after listen* because the customer's
reply is part of the outcome being learned from.

Three exits end a pass early, each writing a terminal state and an audit row:
the uplift check says SKIP, the guardrail says BLOCK, or the customer's reply
says stop.

Phase 4 is a skeleton: diagnose, uplift, decide, listen, and learn are stubs,
and execute simulates. The guardrail and the audit trail are real. That split is
deliberate — the parts that constrain and record the agent ship before the parts
that make it clever. Each step below carries a ``PHASE n`` marker naming what
replaces it.

Two structural notes for the phases that follow:

* **Supabase calls are wrapped individually.** A background task has no caller
  to surface an exception to, so a failed write must degrade the pass rather
  than end it — except where the pass would then be meaningless, which is why
  the whole loop also sits inside one catch that records ``loop_failed``.
* **The service-role client is required here**, not the request-scoped one. The
  loop runs after the HTTP response is sent, and the user's JWT client is dead
  by then.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agent import audit
from app.agent.guardrail import run_guardrail
from app.agent.models import (
    AgentLoopResult,
    CaseStatus,
    DecisionResult,
    DiagnosisResult,
    GuardrailResult,
    ListenResult,
    Playbook,
    StepName,
    UpliftVerdict,
)
from app.agent.steps.decide import run_decide
from app.agent.steps.detect import detect_playbook, extract_amount_at_risk
from app.agent.steps.diagnose import run_diagnose
from app.agent.steps.execute import run_execute
from app.agent.steps.learn import run_learn
from app.agent.steps.listen import run_listen
from app.agent.steps.uplift_check import run_uplift_check
from app.logging import get_logger

logger = get_logger(__name__)

#: A DOWNGRADE verdict names its fallback as ``switch_to_<channel>``.
_DOWNGRADE_PREFIX = "switch_to_"

#: Statuses that mean a case is still the agent's to work on.
_ACTIVE_STATUSES = ["open", "in_flight"]


# ─────────────────────────────────────────────────────────────────────
# Entry point — called by the webhook endpoint as a BackgroundTask
# ─────────────────────────────────────────────────────────────────────


async def process_event(
    event_id: str,
    merchant_id: str,
    supabase_client: Any,
) -> AgentLoopResult | None:
    """Given an event_id, resolve the case and run the agent loop.

    Uses the service-role Supabase client (passed in by the caller) so it can
    read and write across tables after the request context has expired.

    Returns ``None`` for events the agent has no playbook for. An unroutable
    event is a routing gap, not an error, and raising here would fail a webhook
    that Razorpay would then retry indefinitely.
    """
    trace_id = uuid.uuid4().hex
    log = logger.bind(event_id=event_id, merchant_id=merchant_id, trace_id=trace_id)

    try:
        event_resp = supabase_client.table("events").select("*").eq("id", event_id).execute()
    except Exception as exc:  # noqa: BLE001 - a dead DB must not kill the task runner
        log.error("event_fetch_error", error=str(exc))
        return None

    if not event_resp.data:
        log.error("event_not_found")
        return None

    event = dict(event_resp.data[0])

    playbook = detect_playbook(event["event_type"])
    if not playbook:
        log.warning("unrecognised_event_type", event_type=event["event_type"])
        return None

    case = await _get_or_create_case(event, playbook, merchant_id, supabase_client, trace_id)
    if not case:
        log.error("case_creation_failed")
        return None

    return await run_agent_loop(case, event, merchant_id, supabase_client, trace_id)


# ─────────────────────────────────────────────────────────────────────
# The 9-step agent loop
# ─────────────────────────────────────────────────────────────────────


async def run_agent_loop(
    case: dict[str, Any],
    event: dict[str, Any],
    merchant_id: str,
    supabase_client: Any,
    trace_id: str,
) -> AgentLoopResult:
    """Orchestrate the 9 agent steps in order for a given case."""
    case_id = str(case["id"])
    playbook = str(case["playbook"])
    # Validated up front rather than at each return: a case row carrying a
    # playbook name that is not one of the four is a data-integrity bug, and it
    # should surface here rather than nine steps later.
    playbook_enum = Playbook(playbook)
    steps_completed: list[StepName] = []
    log = logger.bind(case_id=case_id, playbook=playbook, trace_id=trace_id)

    # Fetch supporting data once — reused across steps.
    customer = await _fetch_customer(case.get("customer_id"), supabase_client)
    pending_reply = await _fetch_pending_reply(case_id, supabase_client)
    case = _enrich_case(case, event, customer)

    diagnosis: DiagnosisResult | None = None
    uplift: UpliftVerdict | None = None
    decision: DecisionResult | None = None
    guardrail: GuardrailResult | None = None

    try:
        # ── STEP 1: DETECT ─────────────────────────────────────────────
        steps_completed.append(StepName.DETECT)
        await audit.log_case_opened(
            supabase_client,
            case_id,
            merchant_id,
            playbook,
            int(case.get("amount_at_risk_cents") or 0),
            trace_id,
        )
        log.info("step_detect_complete", playbook=playbook)

        # ── STEP 2: DIAGNOSE ───────────────────────────────────────────
        # PHASE 5 replaces the stub with causal DAG traversal + a Gemini call.
        diagnosis = await run_diagnose(case, playbook)
        steps_completed.append(StepName.DIAGNOSE)
        await audit.log_diagnosis(
            supabase_client, case_id, merchant_id, diagnosis.model_dump(), trace_id
        )
        # The audit row keeps the claim; the full evidence goes on the case, which
        # is what the case-detail page reads.
        _update_case(
            supabase_client,
            case_id,
            {"diagnosis": diagnosis.model_dump(mode="json"), "current_step": "diagnose"},
        )
        log.info("step_diagnose_complete", root_cause=diagnosis.root_cause)

        # ── STEP 3: UPLIFT CHECK ───────────────────────────────────────
        # PHASE 9 replaces the stub with a T-learner over a real holdout group.
        uplift = await run_uplift_check(case, diagnosis.model_dump())
        steps_completed.append(StepName.UPLIFT_CHECK)
        await audit.log_uplift_verdict(
            supabase_client, case_id, merchant_id, uplift.model_dump(), trace_id
        )
        _update_case(
            supabase_client,
            case_id,
            {"uplift_bucket": uplift.bucket.value, "current_step": "uplift_check"},
        )
        if uplift.verdict == "SKIP":
            listen, exit_reason = await _hear_pending_reply(
                supabase_client,
                case,
                customer,
                pending_reply,
                trace_id,
                merchant_id,
                steps_completed,
                fallback_reason="Uplift check: not a persuadable case",
            )
            await _close_case(
                supabase_client, case_id, CaseStatus.STOPPED, exit_reason, trace_id, merchant_id
            )
            steps_completed.append(StepName.AUDIT)
            return AgentLoopResult(
                case_id=case_id,
                trace_id=trace_id,
                playbook=playbook_enum,
                steps_completed=steps_completed,
                final_status=CaseStatus.STOPPED,
                diagnosis=diagnosis,
                uplift=uplift,
                listen=listen,
            )
        log.info("step_uplift_complete", verdict=uplift.verdict)

        # ── STEP 4: DECIDE ─────────────────────────────────────────────
        # PHASE 6 replaces the rule-based default arm with a contextual bandit.
        decision = await run_decide(case, diagnosis.model_dump(), playbook)
        steps_completed.append(StepName.DECIDE)
        decision_row = await _write_agent_decision(
            supabase_client, case_id, merchant_id, trace_id, decision, diagnosis, uplift
        )
        decision_dict = decision.model_dump(mode="json")
        decision_dict["id"] = decision_row.get("id")
        await audit.log_decision(supabase_client, case_id, merchant_id, decision_dict, trace_id)
        log.info("step_decide_complete", chosen_arm=decision.chosen_arm)

        # ── STEP 5: GUARDRAIL ──────────────────────────────────────────
        # Fully implemented in Phase 4 and not scheduled for replacement. Later
        # phases add checks; none of them may remove one.
        guardrail = await run_guardrail(case, decision_dict, customer or {}, supabase_client)
        steps_completed.append(StepName.GUARDRAIL)
        await audit.log_guardrail(
            supabase_client, case_id, merchant_id, guardrail.model_dump(), trace_id
        )

        # A DOWNGRADE rejects the channel, not the action. Swap the channel and
        # re-run every check: consent for the replacement has not been verified,
        # and sending on an unverified channel is the exact failure the consent
        # check exists to prevent.
        if guardrail.verdict == "DOWNGRADE":
            decision_dict = _apply_downgrade(decision_dict, guardrail)
            guardrail = await run_guardrail(case, decision_dict, customer or {}, supabase_client)
            await audit.log_guardrail(
                supabase_client, case_id, merchant_id, guardrail.model_dump(), trace_id
            )
            log.info(
                "guardrail_recheck_after_downgrade",
                verdict=guardrail.verdict,
                channel=(decision_dict.get("action_params") or {}).get("channel"),
            )

        log.info("step_guardrail_complete", verdict=guardrail.verdict)

        # A second downgrade means every allowed channel has been tried, so there
        # is nowhere left to fall back to and it is treated as a block.
        if guardrail.verdict != "PASS":
            listen, exit_reason = await _hear_pending_reply(
                supabase_client,
                case,
                customer,
                pending_reply,
                trace_id,
                merchant_id,
                steps_completed,
                fallback_reason=f"Guardrail blocked: {guardrail.blocking_check}",
            )
            await _close_case(
                supabase_client, case_id, CaseStatus.STOPPED, exit_reason, trace_id, merchant_id
            )
            steps_completed.append(StepName.AUDIT)
            return AgentLoopResult(
                case_id=case_id,
                trace_id=trace_id,
                playbook=playbook_enum,
                steps_completed=steps_completed,
                final_status=CaseStatus.STOPPED,
                diagnosis=diagnosis,
                uplift=uplift,
                decision=decision,
                guardrail=guardrail,
                listen=listen,
            )

        # ── STEP 6: EXECUTE ────────────────────────────────────────────
        # FUTURE PHASE swaps the simulated adapters for real API calls; the
        # idempotency key and the attempt row stay exactly as they are.
        execution = await run_execute(case, decision_dict, supabase_client, trace_id)
        steps_completed.append(StepName.EXECUTE)
        await audit.log_execution(
            supabase_client, case_id, merchant_id, execution.model_dump(), trace_id
        )
        _update_case(
            supabase_client,
            case_id,
            {"status": CaseStatus.IN_FLIGHT.value, "current_step": "execute"},
        )
        log.info("step_execute_complete", adapter=execution.adapter, status=execution.status.value)

        # ── STEP 7: LISTEN ─────────────────────────────────────────────
        # PHASE 5 replaces pattern matching with Gemini classification.
        # Runs whether or not a reply is waiting: a pass with no reply still
        # produces a ListenResult (intent UNKNOWN), which keeps the timeline's
        # nine steps honest rather than leaving a gap that reads as a crash.
        listen, final_status, close_reason = await _run_listen_stage(
            supabase_client, case, customer, pending_reply, trace_id, merchant_id
        )
        steps_completed.append(StepName.LISTEN)
        log.info("step_listen_complete", intent=listen.intent.value)

        # ── STEP 8: LEARN ──────────────────────────────────────────────
        # PHASE 6 wires bandit reward updates; PHASE 9 uplift training data;
        # PHASE 10 federated network aggregation.
        await run_learn(case, final_status.value, decision_dict)
        steps_completed.append(StepName.LEARN)

        # ── STEP 9: AUDIT (closure) ────────────────────────────────────
        # Terminal states get a closing row; a case still in flight does not,
        # because the next pass keeps writing to the same trail.
        if final_status is CaseStatus.STOPPED and close_reason:
            await _close_case(
                supabase_client, case_id, final_status, close_reason, trace_id, merchant_id
            )
        steps_completed.append(StepName.AUDIT)

        _mark_event_processed(supabase_client, event)

        log.info(
            "agent_loop_complete",
            final_status=final_status.value,
            steps=len(steps_completed),
        )

        return AgentLoopResult(
            case_id=case_id,
            trace_id=trace_id,
            playbook=playbook_enum,
            steps_completed=steps_completed,
            final_status=final_status,
            diagnosis=diagnosis,
            uplift=uplift,
            decision=decision,
            guardrail=guardrail,
            execution=execution,
            listen=listen,
        )

    except Exception as exc:  # noqa: BLE001 - a failed pass must not lose the trail
        # The loop runs as a background task, so an uncaught exception would
        # vanish into the task runner and leave the case sitting at `open` with
        # no explanation. Record it against the case instead.
        log.exception("agent_loop_failed", error=str(exc))
        await audit.log_agent_step(
            supabase_client,
            case_id,
            merchant_id,
            "audit",
            "system",
            "loop_failed",
            {"error": str(exc), "steps_completed": [s.value for s in steps_completed]},
            trace_id,
        )
        return AgentLoopResult(
            case_id=case_id,
            trace_id=trace_id,
            playbook=playbook_enum,
            steps_completed=steps_completed,
            final_status=CaseStatus.FAILED,
            diagnosis=diagnosis,
            uplift=uplift,
            decision=decision,
            guardrail=guardrail,
            error=str(exc),
        )


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────
async def _run_listen_stage(
    supabase_client: Any,
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    pending_reply: dict[str, Any] | None,
    trace_id: str,
    merchant_id: str,
) -> tuple[ListenResult, CaseStatus, str | None]:
    """Classify any pending reply, apply what it implies, and audit both.

    Returns the classification, the status the case should now hold, and the
    reason to close with (``None`` when the case stays in flight).

    Consent revocation is the one side effect that leaves the case: it writes to
    ``customers``, because "do not contact me" is about the person and not about
    this invoice.
    """
    case_id = str(case["id"])
    log = logger.bind(case_id=case_id, trace_id=trace_id)

    listen = await run_listen(case, pending_reply, supabase_client)
    await audit.log_listen(supabase_client, case_id, merchant_id, listen.model_dump(), trace_id)

    # Mark the reply handled so a later pass cannot re-apply it.
    if pending_reply and listen.reply_id:
        try:
            supabase_client.table("customer_replies").update(
                {
                    "applied_state_update": listen.recommended_state_update or "processed",
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", listen.reply_id).execute()
        except Exception as exc:  # noqa: BLE001
            log.warning("reply_update_error", error=str(exc))

    if listen.opt_out_signal:
        # Revoke consent across all channels — the S6 Sana scenario.
        if customer:
            try:
                updated_consent = {
                    **(customer.get("consent") or {}),
                    "whatsapp": False,
                    "sms": False,
                    "email": False,
                    "marketing": False,
                    "opted_out_at": datetime.now(UTC).isoformat(),
                }
                supabase_client.table("customers").update(
                    {"consent": updated_consent, "updated_at": datetime.now(UTC).isoformat()}
                ).eq("id", customer["id"]).execute()
                await audit.log_agent_step(
                    supabase_client,
                    case_id,
                    merchant_id,
                    "listen",
                    "system",
                    "consent_revoked",
                    {"customer_id": customer["id"], "channels": ["whatsapp", "sms", "email"]},
                    trace_id,
                )
                log.info("consent_revoked", customer_id=customer["id"])
            except Exception as exc:  # noqa: BLE001
                log.warning("consent_revoke_error", error=str(exc))
        return listen, CaseStatus.STOPPED, (
            "Customer opted out — consent revoked across all channels"
        )

    if listen.hardship_signal:
        return listen, CaseStatus.STOPPED, (
            "Customer signalled hardship — recovery paused, human handoff triggered"
        )

    if listen.churn_signal:
        return listen, CaseStatus.STOPPED, (
            "Customer confirmed churn — recovery stopped, handoff to retention team"
        )

    return listen, CaseStatus.IN_FLIGHT, None


async def _hear_pending_reply(
    supabase_client: Any,
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    pending_reply: dict[str, Any] | None,
    trace_id: str,
    merchant_id: str,
    steps_completed: list[StepName],
    *,
    fallback_reason: str,
) -> tuple[ListenResult | None, str]:
    """Run the listen stage on an early exit, if a reply is waiting.

    Listening is perception, not action. A pass that the uplift check or the
    guardrail ends early is forbidden from *sending*, which is no reason to stop
    *hearing* — and without this an inbound "STOP" arriving while the case is
    inside its RBI retry-spacing window would never be honoured, because the
    guardrail returns three steps before LISTEN.

    A reason derived from the customer's own words outranks the machine's:
    "customer opted out" is the truer account of why the case closed than
    "guardrail blocked", so it wins when both are available.
    """
    if not pending_reply:
        return None, fallback_reason

    listen, _status, close_reason = await _run_listen_stage(
        supabase_client, case, customer, pending_reply, trace_id, merchant_id
    )
    steps_completed.append(StepName.LISTEN)
    return listen, close_reason or fallback_reason



async def _get_or_create_case(
    event: dict[str, Any],
    playbook: str,
    merchant_id: str,
    supabase_client: Any,
    trace_id: str,
) -> dict[str, Any] | None:
    """Find an active case for this customer and playbook, or open one.

    Matching on customer + playbook + active status rather than on the trigger
    event is what makes a second pass over the same customer continue the
    existing recovery instead of starting a rival one — the flow that lets an
    inbound reply be picked up by re-running ``process_event``.
    """
    customer_id = await _resolve_customer_id(event, merchant_id, supabase_client)
    if not customer_id:
        logger.warning(
            "customer_not_found_for_event", event_id=event.get("id"), trace_id=trace_id
        )
        return None

    try:
        existing = (
            supabase_client.table("recovery_cases")
            .select("*")
            .eq("customer_id", customer_id)
            .eq("playbook", playbook)
            .in_("status", _ACTIVE_STATUSES)
            .limit(1)
            .execute()
        )
        if existing.data:
            return dict(existing.data[0])
    except Exception as exc:  # noqa: BLE001
        logger.warning("existing_case_lookup_error", error=str(exc), trace_id=trace_id)

    amount = extract_amount_at_risk(event.get("payload") or {}, event["event_type"])
    now = datetime.now(UTC).isoformat()
    new_case = {
        "merchant_id": merchant_id,
        "customer_id": customer_id,
        "playbook": playbook,
        "status": CaseStatus.OPEN.value,
        "amount_at_risk_cents": amount,
        "amount_recovered_cents": 0,
        "opened_at": now,
        "current_step": StepName.DETECT.value,
        "trigger_event_id": event["id"],
        "created_at": now,
        "updated_at": now,
    }
    try:
        resp = supabase_client.table("recovery_cases").insert(new_case).execute()
        return dict(resp.data[0]) if resp.data else None
    except Exception as exc:  # noqa: BLE001
        logger.error("case_creation_error", error=str(exc), trace_id=trace_id)
        return None


async def _resolve_customer_id(
    event: dict[str, Any],
    merchant_id: str,
    supabase_client: Any,
) -> str | None:
    """Resolve the internal customer UUID for an event.

    The FK on ``events`` is checked first because it is authoritative — the
    simulator and the webhook both set it when they can. The payload lookup is
    the fallback for a raw Razorpay event, whose ``customer_id`` is the
    merchant's own external id (``cust_suresh_iyer``), not our UUID.
    """
    if event.get("customer_id"):
        return str(event["customer_id"])

    payload = event.get("payload") or {}
    external_id = (
        payload.get("customer_id")
        or payload.get("customer_external_id")
        or payload.get("external_customer_id")
    )
    if not external_id:
        return None
    try:
        resp = (
            supabase_client.table("customers")
            .select("id")
            .eq("merchant_id", merchant_id)
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        return str(resp.data[0]["id"]) if resp.data else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("customer_resolve_error", external_id=external_id, error=str(exc))
        return None


async def _fetch_customer(customer_id: Any, supabase_client: Any) -> dict[str, Any] | None:
    """Load the customer row, which carries the consent object the guardrail reads."""
    if not customer_id:
        return None
    try:
        resp = supabase_client.table("customers").select("*").eq("id", customer_id).execute()
        return dict(resp.data[0]) if resp.data else None
    except Exception:  # noqa: BLE001
        return None


async def _fetch_pending_reply(case_id: str, supabase_client: Any) -> dict[str, Any] | None:
    """Return the newest reply on this case that no pass has acted on yet.

    ``applied_state_update`` being null is the "unread" marker. Filtering on it
    is what stops a second pass from re-applying an opt-out already honoured.
    """
    try:
        resp = (
            supabase_client.table("customer_replies")
            .select("*")
            .eq("case_id", case_id)
            .is_("applied_state_update", "null")
            .order("received_at", desc=True)
            .limit(1)
            .execute()
        )
        return dict(resp.data[0]) if resp.data else None
    except Exception:  # noqa: BLE001
        return None


def _enrich_case(
    case: dict[str, Any],
    event: dict[str, Any],
    customer: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the case dict the steps actually consume.

    The ``recovery_cases`` row has no ``metadata`` column and no contact
    details, but the guardrail's network-alert check needs the bank and method,
    and the execute adapters need a phone number. Both live on the trigger event
    payload and the customer row, so they are merged in here — once, in the
    orchestrator — rather than having five steps each learn where to look.
    """
    enriched = dict(case)
    enriched["metadata"] = dict(event.get("payload") or {})
    if customer:
        enriched["customer_name"] = customer.get("name")
        enriched["customer_phone"] = customer.get("phone")
        enriched["customer_email"] = customer.get("email")
    return enriched


def _update_case(supabase_client: Any, case_id: str, changes: dict[str, Any]) -> None:
    """Patch a case row, tolerating a write failure.

    A dropped progress update costs the UI a step marker; letting it raise would
    cost the whole recovery.
    """
    try:
        supabase_client.table("recovery_cases").update(
            {**changes, "updated_at": datetime.now(UTC).isoformat()}
        ).eq("id", case_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("case_update_error", case_id=case_id, error=str(exc))


def _mark_event_processed(supabase_client: Any, event: dict[str, Any]) -> None:
    """Stamp ``events.processed_at`` so a backfill can tell what the agent has seen."""
    if event.get("processed_at"):
        return
    try:
        supabase_client.table("events").update(
            {"processed_at": datetime.now(UTC).isoformat()}
        ).eq("id", event["id"]).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("event_processed_update_error", error=str(exc))


async def _write_agent_decision(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    trace_id: str,
    decision: DecisionResult,
    diagnosis: DiagnosisResult,
    uplift: UpliftVerdict,
) -> dict[str, Any]:
    """Write the ``agent_decisions`` row for the decide step.

    The row carries the diagnosis and uplift alongside the chosen arm on
    purpose: the three together are the reasoning behind one action, and
    reconstructing them from separate tables by timestamp is exactly the kind of
    join that goes wrong when two passes run close together.
    """
    now = datetime.now(UTC).isoformat()
    row = {
        "case_id": case_id,
        "merchant_id": merchant_id,
        "step_number": 4,
        "step_name": StepName.DECIDE.value,
        "decision_source": decision.decision_source.value,
        "bandit_chosen_arm": decision.chosen_arm,
        "bandit_arm_confidence": decision.arm_confidence,
        "bandit_mode": decision.bandit_mode,
        "bandit_alternatives": [
            alt.model_dump(mode="json") for alt in decision.alternatives_considered
        ],
        "causal_path": diagnosis.causal_path,
        "chosen_action": decision.chosen_arm,
        "action_params": decision.action_params,
        "reasoning": decision.reasoning,
        "diagnosis_posteriors": diagnosis.model_dump(mode="json"),
        "uplift_estimate": uplift.estimated_lift,
        "created_at": now,
        "updated_at": now,
    }
    try:
        resp = supabase_client.table("agent_decisions").insert(row).execute()
        return dict(resp.data[0]) if resp.data else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("agent_decision_write_error", error=str(exc), trace_id=trace_id)
        return {}


def _apply_downgrade(
    decision_dict: dict[str, Any],
    guardrail: GuardrailResult,
) -> dict[str, Any]:
    """Rewrite a decision's channel to the one the guardrail fell back to.

    ``downgrade_to`` is ``switch_to_<channel>``; anything else is left alone
    rather than guessed at, so a future downgrade meaning something other than a
    channel swap fails closed instead of silently mangling the params.
    """
    target = guardrail.downgrade_to or ""
    if not target.startswith(_DOWNGRADE_PREFIX):
        return decision_dict
    channel = target[len(_DOWNGRADE_PREFIX) :]
    amended = dict(decision_dict)
    params = dict(amended.get("action_params") or {})
    params["downgraded_from"] = params.get("channel")
    params["channel"] = channel
    amended["action_params"] = params
    return amended


async def _close_case(
    supabase_client: Any,
    case_id: str,
    status: CaseStatus,
    reason: str,
    trace_id: str,
    merchant_id: str,
) -> None:
    """Move a case to a terminal status and write its closing audit row.

    The audit row is written here rather than at each call site so that no exit
    path can close a case silently — a closure with no explanation in the trail
    is the one thing this module exists to prevent.
    """
    try:
        supabase_client.table("recovery_cases").update(
            {
                "status": status.value,
                "closed_at": datetime.now(UTC).isoformat(),
                "current_step": "closed",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", case_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("case_close_error", case_id=case_id, error=str(exc))

    await audit.log_case_closed(
        supabase_client, case_id, merchant_id, status.value, reason, trace_id
    )
