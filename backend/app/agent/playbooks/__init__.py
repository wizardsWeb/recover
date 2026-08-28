"""Registry of the four playbook configs.

The lookup is by the same string that lives in ``recovery_cases.playbook`` and
``bandit_arms.playbook``, so a case row can be routed without a translation
table. Unknown names raise rather than defaulting: silently falling back to the
failed-payment envelope would apply consumer message limits to a B2B invoice,
which is the kind of bug that only shows up in a compliance audit.
"""

from collections.abc import Callable
from typing import Any

from app.agent.models import ActionType
from app.agent.playbooks.b2b_overdue import B2B_OVERDUE_CONFIG
from app.agent.playbooks.b2b_overdue import (
    get_default_decision_params as _b2b_overdue_params,
)
from app.agent.playbooks.base import PlaybookConfig
from app.agent.playbooks.checkout_abandonment import CHECKOUT_ABANDONMENT_CONFIG
from app.agent.playbooks.checkout_abandonment import (
    get_default_decision_params as _checkout_abandonment_params,
)
from app.agent.playbooks.failed_payment import FAILED_PAYMENT_CONFIG
from app.agent.playbooks.failed_payment import (
    get_default_decision_params as _failed_payment_params,
)
from app.agent.playbooks.subscription_failure import SUBSCRIPTION_FAILURE_CONFIG
from app.agent.playbooks.subscription_failure import (
    get_default_decision_params as _subscription_failure_params,
)

#: Arm name -> the physical action it resolves to.
#:
#: NOTE — this diverges from ``bandit_arms.action_type`` in the Phase 2 seed for
#: the five link-delivery arms below, which the migration types as
#: ``send_payment_link`` and this map types by delivery channel:
#:
#:   whatsapp_payment_link, sms_payment_link, email_payment_link,
#:   switch_method_upi, whatsapp_payment_link_now
#:
#: The bandit can now select any of them, so the two sources of truth are
#: reachable in the same run. This map wins at runtime because it is what the
#: guardrail's channel-consent check reads; reconciling the seed is a migration.
ARM_TO_ACTION_TYPE: dict[str, ActionType] = {
    "retry_now": ActionType.RETRY_CHARGE,
    "retry_at_optimal_hour": ActionType.RETRY_CHARGE,
    "silent_retry_next_morning": ActionType.RETRY_CHARGE,
    "retry_at_inferred_date": ActionType.RETRY_CHARGE,
    "retry_at_inferred_date_plus_whatsapp_fallback": ActionType.RETRY_CHARGE,
    "immediate_retry": ActionType.RETRY_CHARGE,
    "whatsapp_payment_link": ActionType.SEND_WHATSAPP,
    "whatsapp_payment_link_now": ActionType.SEND_WHATSAPP,
    "whatsapp_saved_cart_no_discount": ActionType.SEND_WHATSAPP,
    "whatsapp_saved_cart_5pct": ActionType.SEND_WHATSAPP,
    "whatsapp_saved_cart_8pct": ActionType.SEND_WHATSAPP,
    "whatsapp_saved_cart_12pct": ActionType.SEND_WHATSAPP,
    "polite_reminder_whatsapp": ActionType.SEND_WHATSAPP,
    "firm_reminder_whatsapp": ActionType.SEND_WHATSAPP,
    "firm_reminder_whatsapp_plus_email": ActionType.SEND_WHATSAPP,
    "partial_payment_offer": ActionType.SEND_PAYMENT_LINK,
    "payment_plan_offer": ActionType.SEND_PAYMENT_LINK,
    "sms_payment_link": ActionType.SEND_SMS,
    "sms_saved_cart": ActionType.SEND_SMS,
    "email_payment_link": ActionType.SEND_EMAIL,
    "email_saved_cart": ActionType.SEND_EMAIL,
    "dunning_email_sequence": ActionType.SEND_EMAIL,
    # Seeded in the b2b_overdue action space but absent from the Phase 4 spec's
    # table; without it the arm would silently resolve to no_op.
    "polite_reminder_email": ActionType.SEND_EMAIL,
    "switch_method_upi": ActionType.SEND_WHATSAPP,
    "mandate_reregistration": ActionType.MANDATE_REREGISTER,
    "human_handoff": ActionType.HUMAN_HANDOFF,
    "escalate_to_human_ar": ActionType.HUMAN_HANDOFF,
    "pause_with_winback": ActionType.NO_OP,
    "accept_promise_to_pay": ActionType.NO_OP,
    "graduated_b2b_sequence": ActionType.GRADUATED_SEQUENCE,
    "no_op": ActionType.NO_OP,
    "suggest_alternate_method": ActionType.SEND_WHATSAPP,
}

PLAYBOOK_CONFIGS: dict[str, PlaybookConfig] = {
    "failed_payment": FAILED_PAYMENT_CONFIG,
    "checkout_abandonment": CHECKOUT_ABANDONMENT_CONFIG,
    "subscription_failure": SUBSCRIPTION_FAILURE_CONFIG,
    "b2b_overdue": B2B_OVERDUE_CONFIG,
}

#: Each playbook module owns the default params for its own arms; this maps the
#: playbook name onto that module's lookup so callers need only the name.
_PARAM_LOOKUPS: dict[str, Callable[[str], dict[str, Any]]] = {
    "failed_payment": _failed_payment_params,
    "checkout_abandonment": _checkout_abandonment_params,
    "subscription_failure": _subscription_failure_params,
    "b2b_overdue": _b2b_overdue_params,
}


def get_playbook_config(playbook: str) -> PlaybookConfig:
    """Return the config for ``playbook``, or raise if it is not one of the four."""
    if playbook not in PLAYBOOK_CONFIGS:
        raise ValueError(f"Unknown playbook: {playbook}")
    return PLAYBOOK_CONFIGS[playbook]


def get_default_action_params(playbook: str, arm: str) -> dict[str, Any]:
    """Return the default ``action_params`` for one arm of one playbook.

    An unknown arm yields ``{}`` rather than raising: the decide step is
    allowed to propose an arm this table has not caught up with, and an empty
    param dict degrades to the adapter's own defaults instead of killing the
    loop.
    """
    lookup = _PARAM_LOOKUPS.get(playbook)
    return lookup(arm) if lookup else {}


__all__ = [
    "ARM_TO_ACTION_TYPE",
    "B2B_OVERDUE_CONFIG",
    "CHECKOUT_ABANDONMENT_CONFIG",
    "FAILED_PAYMENT_CONFIG",
    "PLAYBOOK_CONFIGS",
    "SUBSCRIPTION_FAILURE_CONFIG",
    "PlaybookConfig",
    "get_default_action_params",
    "get_playbook_config",
]
