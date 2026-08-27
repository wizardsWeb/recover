"""Playbook: a recurring mandate failed to charge.

The lever is timing against the payer's cash cycle. A retry two days before
salary lands fails for the same reason the first one did and burns one of the
three retries RBI allows per cycle; the same retry two days *after* usually
succeeds with no message sent at all. That is why the default arm waits for the
inferred date rather than retrying immediately.

The 15-day window covers one full salary cycle plus slack. Past that, the
mandate is more likely broken than the balance low, and the answer is a human.
"""

from typing import Any

from app.agent.models import Playbook
from app.agent.playbooks.base import PlaybookConfig

SUBSCRIPTION_FAILURE_CONFIG = PlaybookConfig(
    playbook=Playbook.SUBSCRIPTION_FAILURE,
    arms=[
        "immediate_retry",
        "retry_at_inferred_date",
        "retry_at_inferred_date_plus_whatsapp_fallback",
        "whatsapp_payment_link_now",
        "dunning_email_sequence",
        "mandate_reregistration",
        "pause_with_winback",
        "human_handoff",
    ],
    default_arm="retry_at_inferred_date",  # wait for the money, don't burn a retry
    max_total_attempts=3,
    max_messages_per_day=1,
    max_messages_per_week=3,
    max_discount_pct=0.0,
    rbi_max_retries_per_cycle=3,
    rbi_min_hours_between_retries=24,
    hard_stop_after_days=15,
    channels_allowed=["whatsapp", "email", "sms"],
    human_escalation_after_attempts=2,  # subscribers are high-LTV; escalate early
)


def get_default_decision_params(arm: str) -> dict[str, Any]:
    """Returns the default action_params for a given arm name."""
    defaults: dict[str, dict[str, Any]] = {
        "immediate_retry": {"delay_minutes": 0},
        "retry_at_inferred_date": {"schedule": "inferred_salary_date", "target_hour": 9},
        "retry_at_inferred_date_plus_whatsapp_fallback": {
            "schedule": "inferred_salary_date",
            "target_hour": 9,
            "fallback": {"channel": "whatsapp", "after_hours": 24},
        },
        "whatsapp_payment_link_now": {"channel": "whatsapp", "link_expiry_hours": 48},
        "dunning_email_sequence": {"channel": "email", "steps": 3, "gap_days": 3},
        "mandate_reregistration": {"channel": "whatsapp", "link_expiry_hours": 72},
        "pause_with_winback": {"pause_months": 3, "winback_after_days": 90},
        "human_handoff": {"queue": "retention", "sla_hours": 48},
    }
    return defaults.get(arm, {})
