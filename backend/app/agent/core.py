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
says stop. Everything else runs to the end.

Phase 4 is a skeleton: diagnose, uplift, decide, listen, and learn are stubs,
and execute simulates. The guardrail and the audit trail are real. That split is
deliberate — the parts that constrain and record the agent ship before the parts
that make it clever.
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

#: Channels the agent may fall back to, in the order a DOWNGRADE walks them.
_DOWNGRADE_PREFIX = "switch_to_"


async def process_event(
    event_id: str,
    merchant_id: str,
    supabase_client: Any,
) -> AgentLoopResult | None:
    """Entry point: given an event_id, create/find the case and run the agent loop.

    Called by the webhook endpoint as a BackgroundTask. Returns ``None`` for
    events the agent has no playbook for — an unroutable event is a routing gap,
    not an error, and raising here would fail a webhook Razorpay would then
    retry forever.
    """
    trace_id = uuid.uuid4().hex

    event_resp = supabase_client.table("events").select("*").eq("id", event_id).execute()
    if not event_resp.data:
        logger.error("event_not_found", event_id=event_id, trace_id=trace_id)
        return None
    event = event_resp.data[0]

    playbook = detect_playbook(event["event_type"])
    if not playbook:
        logger.warning(
            "unrecognised_event_type", event_type=event["event_type"], trace_id=trace_id
        )
        return None

    case = await _get_or_create_case(event, playbook, merchant_id, supabase_client, trace_id)
    if not case:
        return None

    return await run_agent_loop(case, event, merchant_id, supabase_client, trace_id)


async def run_agent_loop(
    case: dict[str, Any],
    event: dict[str, Any],
    merchant_id: str,
    supabase_client: Any,
    trace_id: str,
) -> AgentLoopResult:
    """Run the 9-step agent loop for a given case."""
    case_id = str(case["id"])
    playbook = str(case["playbook"])
    # Validated up front rather than at each return: a case row carrying a
    # playbook name that is not one of the four is a data-integrity bug, and it
    # should surface here rather than nine steps later.
    playbook_enum = Playbook(playbook)
    steps_completed: list[StepName] = []
    log = logger.bind(case_id=case_id, playbook=playbook, trace_id=trace_id)

    # Supporting data the steps need but should not each go and fetch.
    customer = await _fetch_customer(case.get("customer_id"), supabase_client)
    pending_reply = await _fetch_pending_reply(case_id, supabase_client)
    case = _enrich_case(case, event, customer)

    diagnosis: DiagnosisResult | None = None
    uplift: UpliftVerdict | None = None
    decision: DecisionResult | None = None
    guardrail: GuardrailResult | None = None

    try:
        # ─── STEP 1: DETECT ────────────────────────────────────────────
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

        # ─── STEP 2: DIAGNOSE ──────────────────────────────────────────
        diagnosis = await run_diagnose(case, playbook)
        steps_completed.append(StepName.DIAGNOSE)
        await audit.log_diagnosis(
            supabase_client, case_id, merchant_id, diagnosis.model_dump(), trace_id
        )
        # The full diagnosis lives on the case; the audit row keeps only the claim.
        supabase_client.table("recovery_cases").update(
            {"diagnosis": diagnosis.model_dump(mode="json"), "current_step": "diagnose"}
        ).eq("id", case_id).execute()
        log.info("step_diagnose_complete", root_cause=diagnosis.root_cause)

        # ─── STEP 3: UPLIFT CHECK ──────────────────────────────────────
        uplift = await run_uplift_check(case, diagnosis.model_dump())
        steps_completed.append(StepName.UPLIFT_CHECK)
        await audit.log_uplift_verdict(
            supabase_client, case_id, merchant_id, uplift.model_dump(), trace_id
        )
        supabase_client.table("recovery_cases").update(
            {"uplift_bucket": uplift.bucket.value, "current_step": "uplift_check"}
        ).eq("id", case_id).execute()
        if uplift.verdict == "SKIP":
            await _close_case(
                supabase_client,
                case_id,
                CaseStatus.STOPPED,
                "Uplift check: not a persuadable case",
                trace_id,
                merchant_id,
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
            )
        log.info("step_uplift_complete", verdict=uplift.verdict)

        # ─── STEP 4: DECIDE ────────────────────────────────────────────
        decision = await run_decide(case, diagnosis.model_dump(), playbook)
        steps_completed.append(StepName.DECIDE)
        decision_row = await _write_agent_decision(
            supabase_client, case_id, merchant_id, trace_id, decision, diagnosis, uplift
        )
        decision_dict = decision.model_dump(mode="json")
        decision_dict["id"] = decision_row.get("id")
        await audit.log_decision(supabase_client, case_id, merchant_id, decision_dict, trace_id)
        log.info("step_decide_complete", chosen_arm=decision.chosen_arm)

        # ─── STEP 5: GUARDRAIL ─────────────────────────────────────────
        guardrail = await run_guardrail(case, decision_dict, customer or {}, supabase_client)
        steps_completed.append(StepName.GUARDRAIL)
        await audit.log_guardrail(
            supabase_client, case_id, merchant_id, guardrail.model_dump(), trace_id
        )

        # A DOWNGRADE is not a rejection of the action, only of the channel it
        # picked. Swap the channel and re-run the checks once: consent for the
        # replacement channel has not been verified yet, and sending on an
        # unverified channel is the exact failure this check exists to prevent.
        if guardrail.verdict == "DOWNGRADE":
            decision_dict = _apply_downgrade(decision_dict, guardrail)
            guardrail = await run_guardrail(case, decision_dict, customer or {}, supabase_client)
            await audit.log_guardrail(
                supabase_client, case_id, merchant_id, guardrail.model_dump(), trace_id
            )
            log.info(
                "guardrail_recheck_after_downgrade",
                verdict=guardrail.verdict,
                channel=decision_dict.get("action_params", {}).get("channel"),
            )

        log.info("step_guardrail_complete", verdict=guardrail.verdict)

        # A second downgrade means every allowed channel has been tried; there is
        # nowhere left to fall back to, so it is treated as a block.
        if guardrail.verdict != "PASS":
            await _close_case(
                supabase_client,
                case_id,
                CaseStatus.STOPPED,
                f"Guardrail blocked: {guardrail.blocking_check}",
                trace_id,
                merchant_id,
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
            )

        # ─── STEP 6: EXECUTE ───────────────────────────────────────────
        execution = await run_execute(case, decision_dict, supabase_client, trace_id)
        steps_completed.append(StepName.EXECUTE)
        await audit.log_execution(
            supabase_client, case_id, merchant_id, execution.model_dump(), trace_id
        )
        supabase_client.table("recovery_cases").update(
            {"status": CaseStatus.IN_FLIGHT.value, "current_step": "execute"}
        ).eq("id", case_id).execute()
        log.info("step_execute_complete", adapter=execution.adapter, status=execution.status.value)

        # ─── STEP 7: LISTEN ────────────────────────────────────────────
        # Runs whether or not a reply is waiting. A pass with no reply still
        # produces a ListenResult (intent UNKNOWN), which keeps the timeline's
        # nine steps honest rather than showing a gap that looks like a crash.
        listen = await run_listen(case, pending_reply, supabase_client)
        steps_completed.append(StepName.LISTEN)
        if pending_reply:
            await audit.log_listen(
                supabase_client, case_id, merchant_id, listen.model_dump(), trace_id
            )
        final_status = await _apply_listen_result(
            supabase_client, case, customer, pending_reply, listen, trace_id, merchant_id
        )
        log.info("step_listen_complete", intent=listen.intent.value, final_status=final_status)

        # ─── STEP 8: LEARN ─────────────────────────────────────────────
        await run_learn(case, final_status.value, decision_dict)
        steps_completed.append(StepName.LEARN)

        # ─── STEP 9: AUDIT ─────────────────────────────────────────────
        # Terminal states get a closing row; a case still in flight does not,
        # because the next pass will keep writing to the same trail.
        if final_status is not CaseStatus.IN_FLIGHT:
            await _close_case(
                supabase_client,
                case_id,
                final_status,
                listen.recommended_state_update or "Loop completed",
                trace_id,
                merchant_id,
            )
        steps_completed.append(StepName.AUDIT)

        _mark_event_processed(supabase_client, event)

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
        # vanish into the task runner. Record it against the case instead and
        # hand back a result that says which step it died on.
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


# ---------------------------------------------------------------------------
# Case and supporting-data helpers
# ---------------------------------------------------------------------------


async def _get_or_create_case(
    event: dict[str, Any],
    playbook: str,
    merchant_id: str,
    supabase_client: Any,
    trace_id: str,
) -> dict[str, Any] | None:
    """Find the case this event already opened, or open one.

    Phase 2's simulator writes a ``recovery_cases`` row when it fires a
    scenario, so the common path is a lookup by ``trigger_event_id``. A real
    Razorpay webhook has no such row, which is why the create branch exists —
    and why the lookup comes first: processing the same event twice must not
    open a second case against the same customer.
    """
    existing = (
        supabase_client.table("recovery_cases")
        .select("*")
        .eq("trigger_event_id", event["id"])
        .limit(1)
        .execute()
    )
    if existing.data:
        return dict(existing.data[0])

    customer_id = event.get("customer_id")
    if not customer_id:
        # recovery_cases.customer_id is NOT NULL, and a recovery with no one to
        # recover from is not a case. Drop it loudly rather than inventing a row.
        logger.warning("event_without_customer", event_id=event["id"], trace_id=trace_id)
        return None

    row = {
        "merchant_id": merchant_id,
        "customer_id": customer_id,
        "playbook": playbook,
        "status": CaseStatus.OPEN.value,
        "amount_at_risk_cents": extract_amount_at_risk(
            event.get("payload") or {}, event["event_type"]
        ),
        "current_step": StepName.DETECT.value,
        "trigger_event_id": event["id"],
    }
    created = supabase_client.table("recovery_cases").insert(row).execute()
    if not created.data:
        logger.error("case_create_failed", event_id=event["id"], trace_id=trace_id)
        return None
    return dict(created.data[0])


async def _fetch_customer(customer_id: Any, supabase_client: Any) -> dict[str, Any] | None:
    """Load the customer row, which carries the consent object the guardrail reads."""
    if not customer_id:
        return None
    resp = supabase_client.table("customers").select("*").eq("id", customer_id).limit(1).execute()
    return dict(resp.data[0]) if resp.data else None


async def _fetch_pending_reply(case_id: str, supabase_client: Any) -> dict[str, Any] | None:
    """Return the newest reply on this case that no pass has acted on yet.

    ``applied_state_update`` being null is the "unread" marker. Filtering on it
    is what stops a second pass from re-applying an opt-out that was already
    honoured — harmless here, but not once the update has side effects.
    """
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


def _mark_event_processed(supabase_client: Any, event: dict[str, Any]) -> None:
    """Stamp ``events.processed_at`` so a backfill can tell what the agent has seen."""
    if event.get("processed_at"):
        return
    supabase_client.table("events").update(
        {"processed_at": datetime.now(UTC).isoformat()}
    ).eq("id", event["id"]).execute()


# ---------------------------------------------------------------------------
# Decision, guardrail and state-transition helpers
# ---------------------------------------------------------------------------


async def _write_agent_decision(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    trace_id: str,
    decision: DecisionResult,
    diagnosis: DiagnosisResult,
    uplift: UpliftVerdict,
) -> dict[str, Any]:
    """Write the ``agent_decisions`` row for this pass's decide step.

    The row carries the diagnosis and uplift alongside the chosen arm on
    purpose: the three together are the reasoning behind one action, and
    reconstructing them from separate tables by timestamp is exactly the kind of
    join that goes wrong when two passes run close together.
    """
    count_resp = (
        supabase_client.table("agent_decisions")
        .select("id", count="exact")
        .eq("case_id", case_id)
        .execute()
    )
    step_number = (count_resp.count or 0) + 1

    row = {
        "case_id": case_id,
        "merchant_id": merchant_id,
        "step_number": step_number,
        "step_name": StepName.DECIDE.value,
        "decision_source": decision.decision_source.value,
        "bandit_chosen_arm": decision.chosen_arm,
        "bandit_arm_confidence": decision.arm_confidence,
        "bandit_mode": decision.bandit_mode,
        "bandit_alternatives": [
            alt.model_dump(mode="json") for alt in decision.alternatives_considered
        ],
        "causal_path": diagnosis.causal_path,
        "diagnosis_posteriors": {
            "root_cause": diagnosis.root_cause,
            "posterior_probability": diagnosis.posterior_probability,
            "alternative_hypotheses": diagnosis.alternative_hypotheses,
        },
        "chosen_action": decision.action_type.value,
        "action_params": decision.action_params,
        "reasoning": decision.reasoning,
        "uplift_estimate": uplift.estimated_lift,
    }
    resp = supabase_client.table("agent_decisions").insert(row).execute()
    return dict(resp.data[0]) if resp.data else {}


def _apply_downgrade(
    decision_dict: dict[str, Any],
    guardrail: GuardrailResult,
) -> dict[str, Any]:
    """Rewrite a decision's channel to the one the guardrail fell back to.

    ``downgrade_to`` is ``switch_to_<channel>``; anything else is left alone
    rather than guessed at, so a future downgrade that means something other
    than a channel swap fails closed instead of silently mangling the params.
    """
    target = guardrail.downgrade_to or ""
    if not target.startswith(_DOWNGRADE_PREFIX):
        return decision_dict
    channel = target[len(_DOWNGRADE_PREFIX) :]
    amended = dict(decision_dict)
    params = dict(amended.get("action_params") or {})
    params["channel"] = channel
    params["downgraded_from"] = (decision_dict.get("action_params") or {}).get("channel")
    amended["action_params"] = params
    return amended


async def _apply_listen_result(
    supabase_client: Any,
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    pending_reply: dict[str, Any] | None,
    listen: ListenResult,
    trace_id: str,
    merchant_id: str,
) -> CaseStatus:
    """Turn a classified reply into state, and return the case's resulting status.

    Consent revocation is the one side effect here that leaves the case: it
    writes to ``customers``, because "do not contact me" is about the person and
    not about this invoice. Everything else only closes the case.
    """
    if not pending_reply:
        return CaseStatus.IN_FLIGHT

    status = CaseStatus.IN_FLIGHT

    if listen.opt_out_signal and customer:
        consent = dict(customer.get("consent") or {})
        consent.update(
            {
                "whatsapp": False,
                "sms": False,
                "email": False,
                "marketing": False,
                "opted_out_at": datetime.now(UTC).isoformat(),
            }
        )
        supabase_client.table("customers").update({"consent": consent}).eq(
            "id", customer["id"]
        ).execute()
        await audit.log_agent_step(
            supabase_client,
            str(case["id"]),
            merchant_id,
            "listen",
            "system",
            "consent_revoked",
            {"customer_id": customer["id"], "channels": ["whatsapp", "sms", "email"]},
            trace_id,
        )
        status = CaseStatus.STOPPED
    elif listen.churn_signal or listen.hardship_signal:
        # Both hand the case to a human. There is no `paused` status, and
        # `stopped` is the truthful one: the agent is done with it either way.
        status = CaseStatus.STOPPED

    supabase_client.table("customer_replies").update(
        {"applied_state_update": listen.recommended_state_update or "NONE"}
    ).eq("id", pending_reply["id"]).execute()

    return status


async def _close_case(
    supabase_client: Any,
    case_id: str,
    status: CaseStatus,
    reason: str,
    trace_id: str,
    merchant_id: str,
) -> None:
    """Write a case's terminal state and its closing audit row."""
    supabase_client.table("recovery_cases").update(
        {
            "status": status.value,
            "closed_at": datetime.now(UTC).isoformat(),
            "current_step": StepName.AUDIT.value,
        }
    ).eq("id", case_id).execute()
    await audit.log_case_closed(
        supabase_client, case_id, merchant_id, status.value, reason, trace_id
    )
