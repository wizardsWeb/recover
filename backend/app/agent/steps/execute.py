"""Step 6 — Execute: do the thing, or record that we would have.

Every adapter here writes a row to ``execution_attempts`` and calls nothing.
That is the point: the whole loop — detect through audit — can be exercised
end to end, in a demo or in CI, without a single message reaching a real phone
or a single rupee moving. Each ``FUTURE INTEGRATION`` comment marks exactly
where the real call goes when its phase lands, and ``simulated=True`` on the
result means no report can quietly present a simulated send as a real one.

**Idempotency is the safety property.** ``idempotency_key`` is
``case:trace:action``, and the column is ``UNIQUE``. A retried background task,
a duplicated webhook, or a re-fired scenario therefore cannot charge a card
twice or send the same WhatsApp message twice — the second attempt reads the
first one back instead. The pre-check below is the fast path; the constraint is
the guarantee.

The ``case`` dict this receives is the enriched one built by ``core``: the
``recovery_cases`` row plus customer contact fields and the trigger event's
payload under ``metadata``. Adapters read those with ``.get`` and fall back to
placeholders, so a case missing a phone number still produces a truthful
attempt row rather than a ``KeyError``.

**The copy is written before the dispatch, not inside it.** Any action that puts
words in front of a customer goes through ``_generate_message`` first, and the
generated body is stored on ``request_payload["body"]`` — the same field a real
adapter would send. That ordering is what makes the message auditable: the
timeline shows the exact text, whether or not a send ever happens, and a blocked
or failed adapter cannot leave a message that was written but never recorded.
The generation itself falls back to a neutral, amount-free template, so a Gemini
outage sends something bland rather than something wrong.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agent.guardrail import MESSAGE_ACTIONS
from app.agent.llm import make_gemini_client
from app.agent.models import ActionType, ExecutionResult, ExecutionStatus
from app.agent.playbooks import ARM_TO_ACTION_TYPE, get_default_action_params
from app.agent.prompts.message_prompt import (
    FALLBACK_MESSAGE,
    MESSAGE_SCHEMA,
    build_message_prompt,
)
from app.integrations.razorpay_client import (
    create_payment_link,
    get_razorpay_client,
    retry_subscription_charge,
    simulated_payment_link,
)
from app.logging import get_logger

logger = get_logger(__name__)

# The set of actions that put words in front of a customer is the guardrail's,
# reused rather than restated. They must not drift: an action TRAI governs but
# that generates no copy would be sent with an empty body, and one that
# generates copy without being governed would skip the consent check.

#: The B2B escalation ladder: days overdue -> the arms that step fires.
#:
#: Read as "up to N days". An invoice does not need the same message on day 3
#: and day 30, and a single arm that sent the same reminder for six weeks is the
#: behaviour that trains a customer to ignore it. The ladder is the pattern a
#: human AR clerk already follows — ask nicely, ask firmly, offer to split it,
#: then stop automating and pick up the phone.
#:
#: The day-6 step deliberately fires on two channels. scenarios.md S4 does the
#: same ("Simultaneously: email fires with same content, more formal"), and a
#: B2B contact that has to reach an accounts-payable desk is more likely to land
#: if it arrives in both places.
GRADUATED_B2B_LADDER: tuple[tuple[int, tuple[str, ...]], ...] = (
    (5, ("polite_reminder_whatsapp",)),
    (12, ("firm_reminder_whatsapp", "email_payment_link")),
    (20, ("partial_payment_offer",)),
)

#: Past the last rung, automation stops deciding and a person takes it.
GRADUATED_B2B_FINAL: tuple[str, ...] = ("escalate_to_human_ar",)

#: LTV boundaries in paise, for the one context feature the prompt takes as a
#: bucket rather than a number. A model handed "2700000" reasons about the digits;
#: handed "high" it reasons about the customer.
_LTV_HIGH_CENTS = 1_000_000  # Rs 10,000
_LTV_MEDIUM_CENTS = 200_000  # Rs 2,000

#: ``execution_attempts.status`` accepts values this enum does not model
#: (``pending``, ``cancelled``). Reading one back from the idempotency cache
#: must not raise, so anything unrecognised is reported as a failure — the
#: conservative reading, since an attempt that is not known to have succeeded
#: should never be counted as a success.
_DB_STATUS_TO_ENUM: dict[str, ExecutionStatus] = {
    "success": ExecutionStatus.SUCCESS,
    "failure": ExecutionStatus.FAILURE,
    "simulated": ExecutionStatus.SIMULATED,
    "skipped": ExecutionStatus.SKIPPED,
}


def _to_execution_status(value: Any) -> ExecutionStatus:
    """Map a stored status string onto the enum, defaulting to FAILURE."""
    return _DB_STATUS_TO_ENUM.get(str(value), ExecutionStatus.FAILURE)


async def run_execute(
    case: dict[str, Any],
    decision: dict[str, Any],
    supabase_client: Any,
    trace_id: str,
    customer: dict[str, Any] | None = None,
    merchant: dict[str, Any] | None = None,
) -> ExecutionResult:
    """Dispatch the chosen action to the appropriate simulated adapter.

    ``customer`` and ``merchant`` are optional and only feed message generation.
    Without them the copy is still written, just with less context — which is
    the right degradation, because an action the guardrail already cleared
    should not be cancelled by a missing merchant row.
    """
    action_type = decision.get("action_type", "no_op")
    idempotency_key = f"{case['id']}:{trace_id}:{action_type}"

    # Check idempotency — don't re-execute if already attempted with this key.
    existing = (
        supabase_client.table("execution_attempts")
        .select("id", "status")
        .eq("idempotency_key", idempotency_key)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        return ExecutionResult(
            action_type=ActionType(action_type),
            adapter="idempotency_cache",
            status=_to_execution_status(row["status"]),
            idempotency_key=idempotency_key,
            request_payload={"cached": True},
            response_payload={"cached_execution_id": row["id"]},
            simulated=True,
        )

    # Written before the dispatch so the body is on the attempt row regardless
    # of what the adapter does with it. Non-messaging actions skip this entirely.
    message = (
        await _generate_message(
            str(decision.get("chosen_arm") or action_type),
            case,
            customer,
            merchant,
            decision.get("action_params") or {},
            supabase_client,
        )
        if action_type in MESSAGE_ACTIONS
        else None
    )

    # The B2B ladder is several sends behind one decision, so it writes its own
    # attempt rows and returns a summary of them.
    if action_type == ActionType.GRADUATED_SEQUENCE.value:
        return await _run_graduated_sequence(
            case, decision, supabase_client, trace_id, idempotency_key, customer, merchant
        )

    adapter, result = await _dispatch(action_type, case, decision, trace_id, get_razorpay_client())
    if message is not None:
        _attach_message(result, message)
        _substitute_payment_link(result)

    _write_attempt(
        supabase_client,
        case,
        decision,
        action_type=action_type,
        adapter=adapter,
        result=result,
        idempotency_key=idempotency_key,
    )

    return ExecutionResult(
        action_type=ActionType(action_type),
        adapter=adapter,
        status=_to_execution_status(result["status"]),
        idempotency_key=idempotency_key,
        request_payload=result["request_payload"],
        response_payload=result["response_payload"],
        simulated=_was_simulated(result),
    )


async def _payment_link_adapter(
    case: dict[str, Any],
    rzp: Any,
    *,
    channel: str,
    description: str,
) -> tuple[str, dict[str, Any]]:
    """Mint a payment link, really if possible and plausibly if not.

    Shared by ``send_payment_link`` and ``mandate_reregister`` because they are
    the same call with a different description — the difference between "pay this"
    and "update your card" is what the link says, not which API it comes from.

    ``reference_id`` is the case id. That is the join the ``payment.captured``
    webhook uses to find this case when the customer pays, so it is the single
    field that closes the loop, and it is why the amount and the case are read
    from the same row rather than passed separately.
    """
    amount_cents = int(case.get("amount_at_risk_cents") or 0)
    request = {
        "amount": amount_cents,
        "currency": "INR",
        "description": description,
        "customer": {"name": case.get("customer_name", "Customer")},
        "channel": channel,
        "reference_id": case["id"],
    }

    if rzp is None or amount_cents <= 0:
        # A zero-amount link is one Razorpay would reject, and a case whose
        # amount never parsed is exactly the case that produces one.
        return "razorpay_payment_links_simulated", {
            "request_payload": request,
            "response_payload": {**simulated_payment_link(), "status": "created"},
            "status": "success",
        }

    link = await create_payment_link(
        rzp,
        amount_cents=amount_cents,
        customer_name=str(case.get("customer_name") or "Customer"),
        customer_phone=case.get("customer_phone"),
        customer_email=case.get("customer_email"),
        description=description,
        reference_id=str(case["id"]),
        notes={"case_id": str(case["id"]), "playbook": str(case.get("playbook") or "")},
    )
    simulated = bool(link.get("simulated", True))
    adapter = "razorpay_payment_links_simulated" if simulated else "razorpay_payment_links"
    return adapter, {
        "request_payload": request,
        "response_payload": {
            "id": link.get("id", ""),
            "short_url": link.get("short_url", ""),
            "payment_link_url": link.get("short_url", ""),
            "status": link.get("status", "created"),
            "simulated": simulated,
        },
        "status": "success",
    }


#: The literal the message prompt is given in place of a URL. The real link does
#: not exist yet when the copy is written — see `_generate_message` — so the model
#: is told to write this and the adapter swaps it afterwards.
PAYMENT_LINK_PLACEHOLDER = "[payment link]"


def _substitute_payment_link(result: dict[str, Any]) -> None:
    """Put the minted URL into the copy that was written before it existed.

    The ordering is deliberate and explained in ``_generate_message``: asking a
    model to write a URL it has not been given is the fastest way to get a
    hallucinated one in front of a customer. So the copy is written with a
    placeholder and the real ``short_url`` replaces it here, once the adapter has
    actually got one.

    If no link was minted — a WhatsApp-only arm, say — the placeholder is
    removed rather than left in. A customer reading "pay here: [payment link]"
    is worse than one reading a message that simply does not offer a link.
    """
    body = result["request_payload"].get("body")
    if not isinstance(body, str) or PAYMENT_LINK_PLACEHOLDER not in body:
        return

    short_url = str(result["response_payload"].get("short_url") or "")
    if short_url:
        result["request_payload"]["body"] = body.replace(PAYMENT_LINK_PLACEHOLDER, short_url)
        result["response_payload"]["payment_link_url"] = short_url
        return

    cleaned = body.replace(PAYMENT_LINK_PLACEHOLDER, "").replace("  ", " ").strip()
    result["request_payload"]["body"] = cleaned
    logger.info("payment_link_placeholder_dropped", reason="no_link_minted")


def _was_simulated(result: dict[str, Any]) -> bool:
    """Whether this attempt reached a real provider.

    Defaults to ``True`` on a missing flag, which is the safe direction: an
    adapter that forgets to say gets reported as simulated, and the failure mode
    is under-claiming rather than presenting a simulated send as a real one.
    """
    return bool(result["response_payload"].get("simulated", True))


def _ltv_bucket(ltv_cents: Any) -> str:
    """Coarse LTV band for the message prompt."""
    value = int(ltv_cents or 0)
    if value >= _LTV_HIGH_CENTS:
        return "high"
    if value >= _LTV_MEDIUM_CENTS:
        return "medium"
    return "low"


def _order_context(case: dict[str, Any], customer: dict[str, Any] | None) -> str:
    """One line naming what the customer is actually being asked to pay for.

    Generic copy ("your recent payment") converts far worse than copy that names
    the thing — Priya's serum, Meera's 60 crates, Aarav's coaching. Each playbook
    keeps that detail in a different place, so the lookup is per event shape
    rather than one hopeful ``.get``.
    """
    metadata = case.get("metadata") or {}
    customer_meta = (customer or {}).get("metadata") or {}

    items = metadata.get("items")
    if isinstance(items, list) and items:
        names = [str(item.get("name") or item.get("title") or "item") for item in items]
        return ", ".join(names)

    if metadata.get("invoice_id"):
        return (
            f"invoice {metadata['invoice_id']}, {metadata.get('invoice_items', 'goods supplied')}, "
            f"due {metadata.get('due_date', 'earlier')}, "
            f"{metadata.get('days_overdue', 'several')} days overdue"
        )

    if customer_meta.get("subscription_purpose"):
        purpose = str(customer_meta["subscription_purpose"]).replace("_", " ")
        child = customer_meta.get("child_name")
        return f"{child}'s {purpose} subscription, monthly" if child else f"{purpose} subscription"

    return str(customer_meta.get("order_contents") or "your order")


def _invoice_context(case: dict[str, Any]) -> dict[str, Any] | None:
    """Invoice fields for the message prompt, or ``None`` for a consumer case."""
    metadata = case.get("metadata") or {}
    if case.get("playbook") != "b2b_overdue" or not metadata.get("invoice_id"):
        return None
    return {
        "invoice_id": metadata.get("invoice_id"),
        "invoice_description": metadata.get("invoice_items"),
        "days_overdue": days_overdue(case),
    }


async def _generate_message(
    arm_name: str,
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    merchant: dict[str, Any] | None,
    action_params: dict[str, Any],
    supabase_client: Any,
) -> dict[str, Any]:
    """Write the customer-facing copy for one action.

    Never raises and always returns a schema-shaped dict — ``FALLBACK_MESSAGE``
    when Gemini is unavailable. The caller therefore has no success branch to
    forget, and the worst case is a neutral template rather than no message.

    The payment link is passed as the literal ``[payment link]`` placeholder.
    The real short URL is minted inside the payment-link adapter, *after* this
    runs, and asking the model to write a URL it has not been given is the
    fastest way to get a hallucinated one in front of a customer.
    """
    customer = customer or {}
    merchant = merchant or {}
    customer_meta = customer.get("metadata") or {}

    full_name = str(customer.get("name") or case.get("customer_name") or "there")
    prompt = build_message_prompt(
        merchant_name=str(merchant.get("name") or "your merchant"),
        merchant_vertical=str(merchant.get("vertical") or "other"),
        playbook=str(case.get("playbook") or "unknown"),
        arm_name=arm_name,
        amount_inr=int(case.get("amount_at_risk_cents") or 0) // 100,
        customer_first_name=full_name.split()[0],
        preferred_language=str(customer_meta.get("preferred_language") or "hinglish"),
        ltv_bucket=_ltv_bucket(customer.get("ltv_cents")),
        tenure_days=int(customer.get("tenure_days") or 0),
        discount_pct=float(action_params.get("discount_pct") or 0),
        channel=str(action_params.get("channel") or "whatsapp"),
        payment_link_url=PAYMENT_LINK_PLACEHOLDER,
        cart_items=_order_context(case, customer),
        invoice=_invoice_context(case),
    )

    client = make_gemini_client(supabase_client)
    return await client.generate_structured(prompt, MESSAGE_SCHEMA, "message", FALLBACK_MESSAGE)


def _attach_message(result: dict[str, Any], message: dict[str, Any]) -> None:
    """Fold the generated copy into an adapter's request and response payloads.

    Done here rather than inside each adapter so the four messaging branches
    cannot drift — a body that lands on the WhatsApp attempt but not the SMS one
    is a gap the timeline would show as a message that was never written.
    """
    request = result["request_payload"]
    request["body"] = message.get("text", "")
    if "subject" in request:
        request["subject"] = message.get("cta_text") or request["subject"]

    result["response_payload"]["message_generation"] = {
        "tone": message.get("tone"),
        "language": message.get("language"),
        "generation_reasoning": message.get("generation_reasoning"),
        "discount_mentioned": message.get("discount_mentioned"),
        "cta_text": message.get("cta_text"),
        # False whenever the copy came from FALLBACK_MESSAGE, which is what lets
        # the UI label a neutral template as a template rather than as generated.
        "is_llm_generated": message is not FALLBACK_MESSAGE,
    }


def _write_attempt(
    supabase_client: Any,
    case: dict[str, Any],
    decision: dict[str, Any],
    *,
    action_type: str,
    adapter: str,
    result: dict[str, Any],
    idempotency_key: str,
) -> None:
    """Record one attempt.

    ``attempted_at`` and ``completed_at`` are the same instant because nothing
    here waits on a network — when real adapters land they will diverge, and the
    gap becomes the adapter's latency.
    """
    now = datetime.now(UTC).isoformat()
    supabase_client.table("execution_attempts").insert(
        {
            "case_id": case["id"],
            "merchant_id": case["merchant_id"],
            "decision_id": decision.get("id"),
            "action_type": action_type,
            "adapter": adapter,
            "request_payload": result["request_payload"],
            "response_payload": result["response_payload"],
            "status": result["status"],
            "idempotency_key": idempotency_key,
            "attempted_at": now,
            "completed_at": now,
        }
    ).execute()


def days_overdue(case: dict[str, Any]) -> int:
    """How late this invoice is.

    Prefers the figure the event carried, because that is the merchant's own
    ageing calculation and the one on their invoice. Falls back to the time the
    case has been open, which is the closest thing available when the payload
    did not say — and never negative, since a ladder cannot run backwards.
    """
    metadata = case.get("metadata") or {}
    stated = metadata.get("days_overdue")
    if stated is not None:
        try:
            return max(0, int(stated))
        except (TypeError, ValueError):
            pass

    opened_at = case.get("opened_at")
    if not opened_at:
        return 0
    try:
        opened = datetime.fromisoformat(str(opened_at))
    except (TypeError, ValueError):
        return 0
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=UTC)
    return max(0, (datetime.now(UTC) - opened).days)


def graduated_arms_for(days: int) -> tuple[str, ...]:
    """The arms this rung of the ladder fires."""
    for threshold, arms in GRADUATED_B2B_LADDER:
        if days <= threshold:
            return arms
    return GRADUATED_B2B_FINAL


async def _run_graduated_sequence(
    case: dict[str, Any],
    decision: dict[str, Any],
    supabase_client: Any,
    trace_id: str,
    idempotency_key: str,
    customer: dict[str, Any] | None,
    merchant: dict[str, Any] | None,
) -> ExecutionResult:
    """Fire every sub-action for this rung, each as its own attempt row.

    One row per send rather than one row for the sequence. The rows are what the
    TRAI frequency check counts and what the timeline renders, and collapsing
    three sends into one row would understate both — the merchant's cap would be
    measured against a third of the messages actually sent.

    Each sub-action gets its own idempotency key, so a retried pass replays none
    of them rather than replaying the ones that had not been reached yet.
    """
    days = days_overdue(case)
    arms = graduated_arms_for(days)
    log = logger.bind(case_id=case.get("id"), days_overdue=days)
    # One client for the whole ladder rather than one per rung: constructing it
    # reads settings and builds a session, and the ladder can be four sends.
    rzp = get_razorpay_client()

    sub_actions: list[dict[str, Any]] = []
    for arm_name in arms:
        sub_type = ARM_TO_ACTION_TYPE.get(arm_name, ActionType.NO_OP).value
        sub_decision = {
            **decision,
            "chosen_arm": arm_name,
            "action_type": sub_type,
            "action_params": {
                **(decision.get("action_params") or {}),
                **get_default_action_params("b2b_overdue", arm_name),
            },
        }

        message = (
            await _generate_message(
                arm_name,
                case,
                customer,
                merchant,
                sub_decision["action_params"],
                supabase_client,
            )
            if sub_type in MESSAGE_ACTIONS
            else None
        )

        adapter, result = await _dispatch(sub_type, case, sub_decision, trace_id, rzp)
        if message is not None:
            _attach_message(result, message)
            _substitute_payment_link(result)

        _write_attempt(
            supabase_client,
            case,
            decision,
            action_type=sub_type,
            adapter=adapter,
            result=result,
            idempotency_key=f"{idempotency_key}:{arm_name}",
        )

        sub_actions.append(
            {
                "arm_name": arm_name,
                "action_type": sub_type,
                "adapter": adapter,
                "status": result["status"],
                "body": result["request_payload"].get("body"),
            }
        )

    log.info("graduated_sequence_complete", arms=list(arms), sub_actions=len(sub_actions))

    return ExecutionResult(
        action_type=ActionType.GRADUATED_SEQUENCE,
        adapter="graduated_b2b_sequence",
        status=ExecutionStatus.SUCCESS,
        idempotency_key=idempotency_key,
        request_payload={"days_overdue": days, "arms": list(arms)},
        response_payload={"sub_actions": sub_actions, "rung": f"{days}d overdue"},
        simulated=True,
    )


async def _dispatch(
    action_type: str,
    case: dict[str, Any],
    decision: dict[str, Any],
    trace_id: str,
    rzp: Any = None,
) -> tuple[str, dict[str, Any]]:
    """Route to the correct adapter.

    Returns ``(adapter_name, result)``. Both payloads are stored either way, so
    the audit trail shows the shape of the call whether or not one was made.

    ``rzp`` is a Razorpay client or ``None``. Three adapters use it — payment
    links, subscription retries and mandate re-registration — and each falls back
    to its simulated branch when it is absent. The messaging adapters have no
    real branch yet: WhatsApp, SMS and email would need their own providers, and
    the honest thing is that their ``simulated`` flag stays true rather than
    borrowing credibility from the Razorpay integration next to them.

    The adapter *name* records which happened: ``razorpay_payment_links`` for a
    real call, ``razorpay_payment_links_simulated`` for the fallback. A single
    name for both is how a demo ends up unable to say which of its sends were
    real.
    """
    params = decision.get("action_params") or {}
    metadata = case.get("metadata") or {}

    if action_type == "retry_charge":
        subscription_id = str(metadata.get("subscription_id") or "sub_unknown")
        request = {
            "subscription_id": subscription_id,
            # The instrument this retry targets. Recorded because the
            # network aggregator reads it: a retry outcome only says
            # something about a bank if the row remembers which bank it
            # went to, and joining back through the case would tie the
            # cross-merchant read to per-merchant tables.
            "bank": metadata.get("bank"),
            "method": metadata.get("method"),
            "idempotency_key": trace_id,
        }

        if rzp is not None:
            # Razorpay has no "charge this failed subscription again now" call —
            # a subscription retries on its own schedule — so this reads the
            # pending state and records it. Claiming to have forced a retry
            # would be the one line in the audit trail describing an API call
            # nobody can make. The customer-facing recovery is the payment link
            # the same decision mints.
            response = await retry_subscription_charge(rzp, subscription_id)
            simulated = bool(response.get("simulated", True))
            adapter = "razorpay_subscriptions_simulated" if simulated else "razorpay_subscriptions"
            return adapter, {
                "request_payload": request,
                "response_payload": {
                    "subscription_state": response,
                    "retry_scheduled": not simulated,
                    "simulated": simulated,
                },
                "status": "success",
            }

        return "razorpay_subscriptions_simulated", {
            "request_payload": request,
            "response_payload": {
                "status": "queued",
                "retry_scheduled": True,
                "simulated": True,
            },
            "status": "success",
        }

    if action_type == "send_payment_link":
        return await _payment_link_adapter(
            case,
            rzp,
            channel=str(params.get("channel", "whatsapp")),
            description=f"Recovery — case {case['id'][:8]}",
        )

    if action_type == "send_whatsapp":
        # FUTURE INTEGRATION: POST /v1/messages (WhatsApp Business API via Meta or Razorpay)
        return "whatsapp_business_simulated", {
            "request_payload": {
                "to": case.get("customer_phone", "+919999999999"),
                "template_id": params.get("template_id", "recovery_generic_v1"),
                "components": {"channel": params.get("channel", "whatsapp")},
            },
            "response_payload": {
                "message_id": f"wamid.sim_{uuid.uuid4().hex[:8]}",
                "status": "sent",
            },
            "status": "success",
        }

    if action_type == "send_sms":
        # FUTURE INTEGRATION: MSG91 / Twilio SMS
        return "sms_simulated", {
            "request_payload": {
                "to": case.get("customer_phone", "+919999999999"),
                # Overwritten by `_attach_message`; present so the key exists
                # even on the path where generation is skipped.
                "body": "[no message generated]",
            },
            "response_payload": {"sid": f"SMsim{uuid.uuid4().hex[:8]}", "status": "sent"},
            "status": "success",
        }

    if action_type == "send_email":
        # FUTURE INTEGRATION: Resend / SendGrid
        return "email_simulated", {
            "request_payload": {
                "to": case.get("customer_email", "customer@example.com"),
                "subject": "[simulated email]",
            },
            "response_payload": {
                "message_id": f"email_sim_{uuid.uuid4().hex[:8]}",
                "status": "sent",
            },
            "status": "success",
        }

    if action_type == "mandate_reregister":
        # Re-registering a mandate is not an API call the merchant can make on a
        # customer's behalf — the customer has to authorise the new instrument
        # themselves. So this is a payment link whose description says what it is
        # for, which is the actual mechanism, rather than a call to an endpoint
        # that would reject it.
        adapter, result = await _payment_link_adapter(
            case,
            rzp,
            channel="whatsapp",
            description="Update your payment method",
        )
        result["request_payload"]["mandate_id"] = metadata.get("mandate_id", "mand_unknown")
        result["request_payload"]["purpose"] = "mandate_reregistration"
        result["response_payload"]["registration_link"] = result["response_payload"].get(
            "short_url", ""
        )
        return adapter, result

    if action_type == "human_handoff":
        return "human_handoff_system", {
            "request_payload": {
                "case_id": case["id"],
                "priority": "high",
                "reason": "Agent escalated",
            },
            "response_payload": {
                "ticket_id": f"handoff_{uuid.uuid4().hex[:8]}",
                "assigned_to": "retention_team",
            },
            "status": "success",
        }

    # no_op — recorded rather than skipped, because "the agent decided to do
    # nothing" is a decision the timeline has to show.
    return "no_op", {
        "request_payload": {},
        "response_payload": {"message": "No action taken by design"},
        "status": "success",
    }
