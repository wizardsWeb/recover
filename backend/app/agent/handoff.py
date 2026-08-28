"""Handing a case to a person, with everything they need to act on it.

A handoff is not a failure state, and the row this writes is not a log line. It
is a briefing: when the agent stops, someone in a retention or AR team picks the
case up cold, and what they can see decides whether a ₹36,000 subscriber gets a
useful call or a generic one. scenarios.md S5 makes the point — the agent's
contribution there is ₹0 recovered and a customer saved, and it is saved because
the human arrived knowing the LTV, the tenure, and the reason.

**Nothing here calls an LLM.** Every field is read off the case, the customer, or
a fixed table below. That is deliberate: this payload is what a person acts on,
sometimes hours later, and a hallucinated tenure or an invented "suggested
action" is worse than no card at all. Model-written text belongs in the message
to the customer, which a human reviews implicitly by seeing the reply — not in
the internal record they will take at face value.

The row goes into ``execution_attempts`` rather than a table of its own. A
handoff *is* an action the agent took, it belongs on the case timeline beside
the sends, and giving it its own table would mean the timeline had to union two
sources to stay honest.
"""

from datetime import UTC, datetime
from typing import Any

from app.logging import get_logger

logger = get_logger(__name__)

#: Why a case reached a human, and what that person should consider offering.
#:
#: Fixed lists, not generated. Each is a real retention play the merchant can
#: actually make, and they differ by reason because the two situations need
#: opposite things: someone leaving needs a reason to stay, someone struggling
#: needs the pressure taken off.
SUGGESTED_RETENTION_ACTIONS: dict[str, list[str]] = {
    "churn": [
        "offer_3_month_pause",
        "downgrade_to_cheaper_tier",
        "schedule_retention_call",
    ],
    "hardship": [
        "offer_payment_plan",
        "pause_subscription_60_days",
        "waive_current_month",
    ],
    "human_escalation": [
        "review_case_history",
        "contact_customer_directly",
        "adjust_playbook_settings",
    ],
}

#: Human-readable label per reason, so the UI does not have to own this mapping.
REASON_LABELS: dict[str, str] = {
    "churn": "Customer confirmed churn",
    "hardship": "Customer signalled hardship",
    "human_escalation": "Escalated by a human operator",
}

DEFAULT_REASON = "human_escalation"


def build_handoff_payload(
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    reason: str,
    *,
    chosen_arm: str | None = None,
    customer_reply: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Assemble the briefing a person picking this case up needs.

    Amounts stay in paise, the unit every other column uses; the UI formats
    them. Converting here would leave the one number on the page that disagrees
    with the rest of the database.
    """
    customer = customer or {}
    reason_key = reason if reason in SUGGESTED_RETENTION_ACTIONS else DEFAULT_REASON

    return {
        "case_id": str(case.get("id") or ""),
        "reason": reason_key,
        "reason_label": REASON_LABELS[reason_key],
        "note": note,
        "customer": {
            "name": customer.get("name") or case.get("customer_name"),
            "ltv_cents": int(customer.get("ltv_cents") or 0),
            "tenure_days": int(customer.get("tenure_days") or 0),
            "phone": customer.get("phone") or case.get("customer_phone"),
            "email": customer.get("email") or case.get("customer_email"),
        },
        "case_summary": {
            "playbook": case.get("playbook"),
            "amount_at_risk_cents": int(case.get("amount_at_risk_cents") or 0),
            "amount_recovered_cents": int(case.get("amount_recovered_cents") or 0),
            "opened_at": case.get("opened_at"),
            "status": case.get("status"),
        },
        "chosen_arm": chosen_arm,
        # The customer's own words, when there are any. A retention call opens
        # far better from what they actually said than from an intent label.
        "customer_reply": customer_reply,
        "suggested_retention_actions": SUGGESTED_RETENTION_ACTIONS[reason_key],
        "created_at": datetime.now(UTC).isoformat(),
    }


def create_handoff_attempt(
    supabase_client: Any,
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    reason: str,
    *,
    merchant_id: str,
    trace_id: str,
    chosen_arm: str | None = None,
    customer_reply: str | None = None,
    note: str | None = None,
) -> dict[str, Any] | None:
    """Write the handoff row. Returns it, or ``None`` if the write failed.

    Never raises. This runs after a case has already been closed, and a failed
    write should cost the team a card, not undo the closure.

    The idempotency key is keyed on the reason as well as the trace, so a case
    that is escalated by a human after having been handed off for churn gets two
    cards — they are two different briefings — while a replayed pass gets one.
    """
    payload = build_handoff_payload(
        case,
        customer,
        reason,
        chosen_arm=chosen_arm,
        customer_reply=customer_reply,
        note=note,
    )
    now = payload["created_at"]
    case_id = payload["case_id"]

    try:
        supabase_client.table("execution_attempts").insert(
            {
                "case_id": case_id,
                "merchant_id": merchant_id,
                "action_type": "human_handoff",
                "adapter": "human_handoff_system",
                "request_payload": payload,
                "response_payload": {
                    "ticket_id": f"handoff_{trace_id[:8]}_{payload['reason']}",
                    "assigned_to": "retention_team",
                    "status": "awaiting_human",
                },
                "status": "success",
                "idempotency_key": f"{case_id}:{trace_id}:handoff:{payload['reason']}",
                "attempted_at": now,
                "completed_at": now,
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001 - a closed case must stay closed
        logger.warning("handoff_write_error", case_id=case_id, error=str(exc))
        return None

    logger.info(
        "human_handoff_created",
        case_id=case_id,
        reason=payload["reason"],
        ltv_cents=payload["customer"]["ltv_cents"],
        trace_id=trace_id,
    )
    return payload
