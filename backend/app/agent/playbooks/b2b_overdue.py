"""Playbook: a business invoice is past due.

The lever is tone escalation and payment flexibility, played out over a
relationship worth more than any single invoice. Everything about this envelope
is slower than the consumer playbooks: two messages a week, a 45-day window,
and a default arm that is polite rather than firm.

Being wrong here is asymmetric. A too-aggressive reminder on a ₹8L invoice can
cost the account; a too-gentle one costs a few days of float.
"""

from typing import Any

from app.agent.models import Playbook
from app.agent.playbooks.base import PlaybookConfig

B2B_OVERDUE_CONFIG = PlaybookConfig(
    playbook=Playbook.B2B_OVERDUE,
    arms=[
        "polite_reminder_whatsapp",
        "polite_reminder_email",
        "firm_reminder_whatsapp",
        "firm_reminder_whatsapp_plus_email",
        "partial_payment_offer",
        "payment_plan_offer",
        "accept_promise_to_pay",
        "escalate_to_human_ar",
        "graduated_b2b_sequence",
    ],
    default_arm="polite_reminder_whatsapp",  # start at the bottom of the tone ladder
    max_total_attempts=6,  # 45 days at 2/week, with room to stop early
    max_messages_per_day=1,
    max_messages_per_week=2,
    max_discount_pct=0.0,  # B2B negotiates terms, not price
    # No arm retries a charge — there is no mandate on an invoice.
    rbi_max_retries_per_cycle=0,
    rbi_min_hours_between_retries=0,
    hard_stop_after_days=45,
    channels_allowed=["whatsapp", "email"],
    human_escalation_after_attempts=3,
)


def get_default_decision_params(arm: str) -> dict[str, Any]:
    """Returns the default action_params for a given arm name."""
    defaults: dict[str, dict[str, Any]] = {
        "polite_reminder_whatsapp": {
            "channel": "whatsapp",
            "tone": "polite",
            "business_hours_only": True,
        },
        "polite_reminder_email": {"channel": "email", "tone": "polite"},
        "firm_reminder_whatsapp": {
            "channel": "whatsapp",
            "tone": "firm",
            "business_hours_only": True,
        },
        "firm_reminder_whatsapp_plus_email": {
            "channel": "whatsapp",
            "tone": "firm",
            "also_email": True,
            "business_hours_only": True,
        },
        "partial_payment_offer": {
            "channel": "whatsapp",
            "min_partial_pct": 50,
            "link_expiry_hours": 168,
        },
        "payment_plan_offer": {"channel": "whatsapp", "instalments": 3, "gap_days": 15},
        "accept_promise_to_pay": {"followup_after_days": 7},
        "escalate_to_human_ar": {"queue": "accounts_receivable", "sla_hours": 24},
        "graduated_b2b_sequence": {
            "channel": "whatsapp",
            "sequence": [
                {"day": 0, "tone": "polite"},
                {"day": 5, "tone": "firm"},
                {"day": 10, "offer": "partial_payment"},
            ],
            "business_hours_only": True,
        },
    }
    return defaults.get(arm, {})
