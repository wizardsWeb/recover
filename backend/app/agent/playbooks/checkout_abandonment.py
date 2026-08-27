"""Playbook: the cart was filled and never paid for.

The lever is discount magnitude against margin, which is why this is the only
playbook with a non-zero ``max_discount_pct`` — and why the default arm offers
no discount at all. Handing money away is what the bandit has to *earn* the
right to do; a stub that defaults to 12% off would train the merchant to
distrust the agent on day one.

The window is short by design. A cart is cold after two days, and messaging a
customer about a cart they have forgotten is an interruption with no upside.
"""

from typing import Any

from app.agent.models import Playbook
from app.agent.playbooks.base import PlaybookConfig

CHECKOUT_ABANDONMENT_CONFIG = PlaybookConfig(
    playbook=Playbook.CHECKOUT_ABANDONMENT,
    arms=[
        "whatsapp_saved_cart_no_discount",
        "whatsapp_saved_cart_5pct",
        "whatsapp_saved_cart_8pct",
        "whatsapp_saved_cart_12pct",
        "email_saved_cart",
        "sms_saved_cart",
        "suggest_alternate_method",
        "no_op",
    ],
    default_arm="whatsapp_saved_cart_no_discount",  # never discount on a stub decision
    max_total_attempts=3,
    max_messages_per_day=1,
    max_messages_per_week=3,
    max_discount_pct=15.0,
    # No arm in this playbook retries a charge, so the RBI mandate limits do not
    # apply. Zero is the honest value: "no retries are permitted here".
    rbi_max_retries_per_cycle=0,
    rbi_min_hours_between_retries=0,
    hard_stop_after_days=2,
    channels_allowed=["whatsapp", "email", "sms"],
    human_escalation_after_attempts=0,  # a cold cart is never worth a human's time
)


def get_default_decision_params(arm: str) -> dict[str, Any]:
    """Returns the default action_params for a given arm name."""
    defaults: dict[str, dict[str, Any]] = {
        "whatsapp_saved_cart_no_discount": {"channel": "whatsapp", "discount_pct": 0},
        "whatsapp_saved_cart_5pct": {"channel": "whatsapp", "discount_pct": 5},
        "whatsapp_saved_cart_8pct": {"channel": "whatsapp", "discount_pct": 8},
        "whatsapp_saved_cart_12pct": {"channel": "whatsapp", "discount_pct": 12},
        "email_saved_cart": {"channel": "email", "discount_pct": 0},
        "sms_saved_cart": {"channel": "sms", "discount_pct": 0},
        "suggest_alternate_method": {
            "channel": "whatsapp",
            "discount_pct": 0,
            "suggest_methods": ["upi", "netbanking"],
        },
        "no_op": {},
    }
    return defaults.get(arm, {})
