"""Step 1 — Detect: turn an inbound event into a playbook.

This is the only step with no model call, no database read, and no judgement:
an event type maps to exactly one playbook or to nothing. Keeping it that
narrow means the loop's entry point cannot fail in an interesting way, and an
unrecognised event type is a routing gap rather than a crash.
"""

from typing import Any

EVENT_TYPE_TO_PLAYBOOK: dict[str, str] = {
    "payment.failed": "failed_payment",
    "checkout.abandoned": "checkout_abandonment",
    "subscription.charged.failed": "subscription_failure",
    "invoice.overdue": "b2b_overdue",
}

#: Events that mean a case is *over*, not that one should open.
#:
#: Razorpay fires these when a customer actually pays — including when they pay
#: a link the agent itself minted. Routing one to a playbook would open a fresh
#: recovery case against a customer who has just settled, which is both wrong and
#: the most annoying possible way to be wrong. ``process_event`` checks this set
#: before it consults ``EVENT_TYPE_TO_PLAYBOOK``.
#:
#: ``payment_link.paid`` is here as well as the two the brief named: it is what
#: Razorpay fires for a payment link specifically, and the agent's own recoveries
#: are payment links.
TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "payment.captured",
        "subscription.charged",
        "payment_link.paid",
    }
)


def is_terminal_event(event_type: str) -> bool:
    """Whether this event closes a case rather than opening one."""
    return event_type in TERMINAL_EVENT_TYPES


#: Payload keys that carry the money at stake, in the order the four event
#: builders in ``app.simulator.event_generator`` emit them. ``checkout.abandoned``
#: is the odd one out: a cart has a value, not an amount.
_AMOUNT_KEYS = ("amount", "cart_value", "invoice_amount")


def detect_playbook(event_type: str) -> str | None:
    """Maps a Razorpay event type to the correct playbook name.

    Returns ``None`` if unrecognised — ``customer.replied`` and anything Razorpay
    adds later land here, and the caller drops them rather than guessing.
    """
    return EVENT_TYPE_TO_PLAYBOOK.get(event_type)


def extract_amount_at_risk(event_payload: dict[str, Any], event_type: str) -> int:
    """Extract ``amount_at_risk_cents`` from the event payload.

    All amounts in the payload are in paise (cents), matching Razorpay's own
    convention and the ``BIGINT`` columns that store them.

    Returns 0 if not found. That is a deliberate safe default rather than an
    error: a case with an unknown amount is still worth opening, and a recovery
    the agent under-values is a better failure than one it never attempts.
    """
    for key in _AMOUNT_KEYS:
        if key in event_payload:
            value = event_payload[key]
            # bool is an int subclass; `{"amount": True}` must not become 1.
            if isinstance(value, bool):
                continue
            if isinstance(value, int | float) and value > 0:
                return int(value)
    return 0
