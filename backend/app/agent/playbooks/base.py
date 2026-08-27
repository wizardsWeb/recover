"""The shape of a playbook's operating envelope.

A ``PlaybookConfig`` is the answer to two questions the agent asks on every
pass: *what am I allowed to try* (``arms``) and *when must I stop*
(everything else). Keeping both in one frozen-by-convention dataclass rather
than scattering them across the steps means a compliance reviewer can read one
file per playbook and see the whole envelope.

The limits are deliberately per-playbook, not global. A B2B invoice tolerates a
45-day recovery window and two messages a week; an abandoned cart is cold after
48 hours and gets one message a day. A single global cap would have to be the
strictest of the four, which would quietly abandon most of the B2B money.
"""

from dataclasses import dataclass

from app.agent.models import Playbook


@dataclass(frozen=True)
class PlaybookConfig:
    """Action space and guardrail parameters for one playbook."""

    playbook: Playbook
    arms: list[str]  # arm names from bandit_arms table
    default_arm: str  # rule-based fallback arm name
    max_total_attempts: int  # hard stop across entire case
    max_messages_per_day: int  # TRAI guard
    max_messages_per_week: int  # TRAI guard
    max_discount_pct: float  # merchant cap
    rbi_max_retries_per_cycle: int  # RBI mandate rule (for subscription)
    rbi_min_hours_between_retries: int  # RBI mandate rule
    hard_stop_after_days: int  # abandon recovery after this many days
    channels_allowed: list[str]  # "whatsapp", "sms", "email"
    human_escalation_after_attempts: int  # escalate if N attempts unacknowledged
