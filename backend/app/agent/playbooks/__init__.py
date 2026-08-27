"""Registry of the four playbook configs.

The lookup is by the same string that lives in ``recovery_cases.playbook`` and
``bandit_arms.playbook``, so a case row can be routed without a translation
table. Unknown names raise rather than defaulting: silently falling back to the
failed-payment envelope would apply consumer message limits to a B2B invoice,
which is the kind of bug that only shows up in a compliance audit.
"""

from collections.abc import Callable
from typing import Any

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
    "B2B_OVERDUE_CONFIG",
    "CHECKOUT_ABANDONMENT_CONFIG",
    "FAILED_PAYMENT_CONFIG",
    "PLAYBOOK_CONFIGS",
    "SUBSCRIPTION_FAILURE_CONFIG",
    "PlaybookConfig",
    "get_default_action_params",
    "get_playbook_config",
]
