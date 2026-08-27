"""Playbook: a one-time payment failed.

The lever here is *when* and *how hard* to re-ask. The cheapest recovery is a
silent retry the customer never sees, so that is the default arm until the
bandit has evidence that a message earns its interruption.
"""

from typing import Any

from app.agent.models import Playbook
from app.agent.playbooks.base import PlaybookConfig

FAILED_PAYMENT_CONFIG = PlaybookConfig(
    playbook=Playbook.FAILED_PAYMENT,
    arms=[
        "retry_now",
        "retry_at_optimal_hour",
        "silent_retry_next_morning",
        "whatsapp_payment_link",
        "sms_payment_link",
        "email_payment_link",
        "switch_method_upi",
        "no_op",
    ],
    default_arm="silent_retry_next_morning",  # conservative default until bandit learns
    max_total_attempts=3,
    max_messages_per_day=2,
    max_messages_per_week=5,
    max_discount_pct=0.0,
    rbi_max_retries_per_cycle=3,
    rbi_min_hours_between_retries=24,
    hard_stop_after_days=7,
    channels_allowed=["whatsapp", "sms", "email"],
    human_escalation_after_attempts=3,
)


def get_default_decision_params(arm: str) -> dict[str, Any]:
    """Returns the default action_params for a given arm name."""
    defaults: dict[str, dict[str, Any]] = {
        "retry_now": {"delay_minutes": 0},
        "retry_at_optimal_hour": {"target_hour": 9, "target_day_offset": 1},
        "silent_retry_next_morning": {"target_hour": 9, "target_day_offset": 1, "silent": True},
        "whatsapp_payment_link": {"channel": "whatsapp", "link_expiry_hours": 24},
        "sms_payment_link": {"channel": "sms", "link_expiry_hours": 24},
        "email_payment_link": {"channel": "email", "link_expiry_hours": 24},
        "switch_method_upi": {"channel": "whatsapp", "suggest_method": "upi"},
        "no_op": {},
    }
    return defaults.get(arm, {})
