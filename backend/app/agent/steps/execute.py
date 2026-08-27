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
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.agent.models import ActionType, ExecutionResult, ExecutionStatus

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
) -> ExecutionResult:
    """Dispatch the chosen action to the appropriate simulated adapter."""
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

    adapter, result = await _dispatch(action_type, case, decision, trace_id)

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
                "body": "[simulated SMS]",
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
