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

from app.agent.llm import make_gemini_client
from app.agent.models import ActionType, ExecutionResult, ExecutionStatus
from app.agent.prompts.message_prompt import (
    FALLBACK_MESSAGE,
    MESSAGE_SCHEMA,
    build_message_prompt,
)
from app.logging import get_logger

logger = get_logger(__name__)

#: Actions whose payload carries copy a human being will read. Only these get a
#: generated message; a silent retry or a mandate re-registration has no body.
_MESSAGE_ACTIONS: frozenset[str] = frozenset(
    {"send_whatsapp", "send_sms", "send_email", "send_payment_link"}
)

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
        if action_type in _MESSAGE_ACTIONS
        else None
    )

    adapter, result = await _dispatch(action_type, case, decision, trace_id)
    if message is not None:
        _attach_message(result, message)

    # Write execution attempt. `attempted_at` and `completed_at` are the same
    # instant because nothing here waits on a network — when real adapters land
    # they will diverge, and the gap becomes the adapter's latency.
    now = datetime.now(UTC).isoformat()
    attempt_row = {
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
    supabase_client.table("execution_attempts").insert(attempt_row).execute()

    return ExecutionResult(
        action_type=ActionType(action_type),
        adapter=adapter,
        status=_to_execution_status(result["status"]),
        idempotency_key=idempotency_key,
        request_payload=result["request_payload"],
        response_payload=result["response_payload"],
        simulated=True,
    )


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
        payment_link_url="[payment link]",
        cart_items=_order_context(case, customer),
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


async def _dispatch(
    action_type: str,
    case: dict[str, Any],
    decision: dict[str, Any],
    trace_id: str,
) -> tuple[str, dict[str, Any]]:
    """Route to the correct simulated adapter.

    Returns ``(adapter_name, result)`` where the result carries the request we
    would have sent and the response we pretend came back. Both are stored, so
    the audit trail shows the shape of the real call even though no call was
    made.
    """
    params = decision.get("action_params") or {}
    metadata = case.get("metadata") or {}

    if action_type == "retry_charge":
        # FUTURE INTEGRATION: POST /v1/subscriptions/{id}/retry_charge (Razorpay Subscriptions API)
        return "razorpay_subscriptions_simulated", {
            "request_payload": {
                "subscription_id": metadata.get("subscription_id", "sub_unknown"),
                "idempotency_key": trace_id,
            },
            "response_payload": {"status": "queued", "retry_scheduled": True},
            "status": "success",
        }

    if action_type == "send_payment_link":
        # FUTURE INTEGRATION: POST /v1/payment_links (Razorpay Payment Links API)
        link_id = f"plink_sim_{uuid.uuid4().hex[:8]}"
        return "razorpay_payment_links_simulated", {
            "request_payload": {
                "amount": case.get("amount_at_risk_cents", 0),
                "currency": "INR",
                "description": f"Recovery — case {case['id'][:8]}",
                "customer": {"name": case.get("customer_name", "Customer")},
                "channel": params.get("channel", "whatsapp"),
            },
            "response_payload": {
                "id": link_id,
                "short_url": f"https://rzp.io/l/{link_id}",
                "status": "created",
            },
            "status": "success",
        }

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
        # FUTURE INTEGRATION: Razorpay Subscriptions — mandate re-registration flow
        return "razorpay_mandate_simulated", {
            "request_payload": {"mandate_id": metadata.get("mandate_id", "mand_unknown")},
            "response_payload": {
                "status": "reregistration_initiated",
                "registration_link": "https://rzp.io/r/sim",
            },
            "status": "success",
        }

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
