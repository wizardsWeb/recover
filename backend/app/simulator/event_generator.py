"""Razorpay-shaped webhook payload builders for the simulator.

These produce the exact JSON that ``scenarios.md`` shows arriving at Recover, so
the same payload drives the demo, the tests, and (from Phase 3) the real webhook
handler. Getting the shape right here means the ingestion path never has to know
whether an event came from Razorpay or from the simulator.

Two rules keep the output faithful to the script:

* **Key order follows the script.** Python dicts preserve insertion order and
  ``json.dumps`` respects it, so a generated payload rendered in the UI reads
  the same top-to-bottom as the block in ``scenarios.md``.
* **Absent means absent.** A field the script does not show for a given event is
  omitted rather than emitted as ``null`` — ``{"bank": null}`` is a different
  payload from one with no ``bank`` key, and downstream code that does
  ``"bank" in payload`` would be wrong about it.

``merchant_id`` in these payloads is the merchant's *own* slug
(``zenith_learning``), not our UUID primary key — the same distinction as
``customers.external_id``. Our tenancy id lives on the ``events`` row.
"""

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

#: Every scripted amount is in INR; the field is explicit because Razorpay's is.
DEFAULT_CURRENCY = "INR"


def now_ist_iso() -> str:
    """Current time as an ISO 8601 string with the +05:30 offset.

    Used only when a caller does not pin a timestamp. The scenarios all pin
    theirs, because S3 turns on the event landing at 11:34pm on a Saturday.
    """
    return datetime.now(IST).isoformat(timespec="seconds")


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is ``None``, preserving order."""
    return {key: value for key, value in payload.items() if value is not None}


def build_payment_failed_event(
    customer_external_id: str,
    amount_cents: int,
    method: str,
    failure_code: str,
    failure_reason: str | None = None,
    bank: str | None = None,
    extra: dict[str, Any] | None = None,
    *,
    merchant_ref: str | None = None,
    order_id: str | None = None,
    attempted_at: str | None = None,
) -> dict[str, Any]:
    """Build a ``payment.failed`` payload (scenarios.md §S3, §S6).

    ``extra`` is merged in after ``method`` and before the failure fields, which
    is where the script puts the ``card`` block in S3.
    """
    payload: dict[str, Any] = {
        "event": "payment.failed",
        "merchant_id": merchant_ref,
        "customer_id": customer_external_id,
        "order_id": order_id,
        "amount": amount_cents,
        "currency": DEFAULT_CURRENCY,
        "method": method,
    }
    payload = _compact(payload)
    if extra:
        payload.update(extra)
    payload.update(
        _compact(
            {
                "bank": bank,
                "failure_code": failure_code,
                "failure_reason": failure_reason,
                "attempted_at": attempted_at or now_ist_iso(),
            }
        )
    )
    return payload


def build_checkout_abandoned_event(
    customer_external_id: str,
    cart_value_cents: int,
    items: list[dict[str, Any]],
    dropoff_stage: str,
    session_duration_seconds: int,
    *,
    merchant_ref: str | None = None,
    cart_id: str | None = None,
    abandoned_at: str | None = None,
) -> dict[str, Any]:
    """Build a ``checkout.abandoned`` payload (scenarios.md §S2).

    Note the timestamp field is ``abandoned_at``, not ``attempted_at`` — nothing
    was attempted, which is the entire difference between this playbook and the
    failed-payment one.
    """
    return _compact(
        {
            "event": "checkout.abandoned",
            "merchant_id": merchant_ref,
            "customer_id": customer_external_id,
            "cart_id": cart_id,
            "cart_value": cart_value_cents,
            "currency": DEFAULT_CURRENCY,
            "items": items,
            "dropoff_stage": dropoff_stage,
            "session_duration_seconds": session_duration_seconds,
            "abandoned_at": abandoned_at or now_ist_iso(),
        }
    )


def build_subscription_charged_failed_event(
    customer_external_id: str,
    subscription_id: str | None,
    amount_cents: int,
    failure_reason: str,
    method: str | None = None,
    mandate_id: str | None = None,
    bank: str | None = None,
    *,
    merchant_ref: str | None = None,
    failure_code: str | None = None,
    attempted_at: str | None = None,
) -> dict[str, Any]:
    """Build a ``subscription.charged.failed`` payload (scenarios.md §S1, §S5)."""
    return _compact(
        {
            "event": "subscription.charged.failed",
            "merchant_id": merchant_ref,
            "customer_id": customer_external_id,
            "subscription_id": subscription_id,
            "amount": amount_cents,
            "currency": DEFAULT_CURRENCY,
            "failure_code": failure_code,
            "failure_reason": failure_reason,
            "method": method,
            "mandate_id": mandate_id,
            "bank": bank,
            "attempted_at": attempted_at or now_ist_iso(),
        }
    )


def build_invoice_overdue_event(
    customer_external_id: str,
    invoice_id: str,
    amount_cents: int,
    due_date: date,
    days_overdue: int,
    invoice_description: str,
    *,
    merchant_ref: str | None = None,
) -> dict[str, Any]:
    """Build an ``invoice.overdue`` payload (scenarios.md §S4).

    This one has no timestamp: it is raised by the merchant's own ageing cron,
    not by a payment attempt, so ``due_date`` and ``days_overdue`` are what
    locate it in time.
    """
    return _compact(
        {
            "event": "invoice.overdue",
            "merchant_id": merchant_ref,
            "customer_id": customer_external_id,
            "invoice_id": invoice_id,
            "amount": amount_cents,
            "currency": DEFAULT_CURRENCY,
            "due_date": due_date.isoformat(),
            "days_overdue": days_overdue,
            "invoice_items": invoice_description,
        }
    )


# ---------------------------------------------------------------------------
# Customer upsert
# ---------------------------------------------------------------------------


def get_or_create_customer(
    supabase_client: Any,
    merchant_id: str,
    persona: dict[str, Any],
) -> dict[str, Any]:
    """Return the customer row for ``persona``, creating it if absent.

    Select-then-insert rather than ``upsert``: Phase 1 gives
    ``(merchant_id, external_id)`` a plain index, not a UNIQUE constraint, and
    PostgREST's upsert needs a real constraint to resolve the conflict target.
    Adding one would mean altering a frozen table, so the uniqueness is enforced
    here instead — acceptable because the only writer is the simulator, one
    request at a time.

    RLS scopes both statements to the caller's merchant, so a persona loaded by
    one merchant is invisible to (and cannot be reused by) another.
    """
    external_id = persona["external_id"]

    existing = (
        supabase_client.table("customers")
        .select("*")
        .eq("merchant_id", merchant_id)
        .eq("external_id", external_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return dict(existing.data[0])

    metadata = dict(persona.get("metadata") or {})
    # The marker `reset` uses to tell simulator rows from a merchant's own.
    metadata["is_simulator_fixture"] = True
    if persona.get("past_events_summary"):
        metadata["past_events_summary"] = persona["past_events_summary"]

    inserted = (
        supabase_client.table("customers")
        .insert(
            {
                "merchant_id": merchant_id,
                "external_id": external_id,
                "name": persona.get("name"),
                "phone": persona.get("phone"),
                "email": persona.get("email"),
                "ltv_cents": persona.get("ltv_cents", 0),
                "tenure_days": persona.get("tenure_days", 0),
                "consent": persona.get("consent", {}),
                "metadata": metadata,
            }
        )
        .execute()
    )
    return dict(inserted.data[0])
