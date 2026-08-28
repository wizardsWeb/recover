"""Holdout assignment — the control group uplift is measured against.

A small share of eligible cases are deliberately left alone. Nothing is sent,
no arm is pulled, no reward is posted. What happens to them anyway is the only
honest answer to "would this customer have paid without us?", and every
incremental-recovery figure on the ROI page is a comparison against them.

Two properties matter more than the sampling itself:

* **Assignment happens once, on the first pass.** ``run_agent_loop`` runs per
  pass, not per case — a case waiting on a reply is re-entered several times. A
  dice roll on every pass would let a case become a "control" after it had
  already been messaged, and a control that received a WhatsApp is not a
  control. Every number computed from the group would be quietly wrong, in the
  flattering direction.
* **The context is frozen at assignment.** The features are stored on the
  holdout row when it is created, not recomputed when the model trains. The
  time of day a case arrived is part of its context; reading it back at
  training time would record when the trainer ran.

The draw is a real random draw rather than every-twentieth-case: a fixed stride
correlates with arrival order, and arrival order correlates with time of day,
which is one of the features being conditioned on.
"""

import random
from datetime import UTC, datetime
from typing import Any

from app.logging import get_logger

logger = get_logger(__name__)

#: Share of eligible cases held back. Small enough that the cost of not acting
#: stays low, large enough that a demo-scale run produces a usable control.
HOLDOUT_RATE = 0.05


def draw() -> float:
    """The holdout dice roll.

    A named function rather than an inline ``random.random()`` so tests can pin
    it. Seeding the global RNG instead would make every other consumer of
    ``random`` in the same process deterministic too — including the bandit's
    Thompson draw, which has its own test seam and its own reasons.
    """
    return random.random()


#: Steps a case can sit at while still having had nothing done to it.
#: ``_get_or_create_case`` stamps ``detect`` at insert time, so an untouched
#: case is at ``detect``, not at ``NULL`` — checking for absence here would
#: mean no case was ever eligible and the control group stayed permanently
#: empty, with every uplift number silently falling back to "no data".
_UNTOUCHED_STEPS = frozenset({"", "detect"})


def is_first_pass(case: dict[str, Any]) -> bool:
    """Whether anything has been done to this case yet.

    ``current_step`` advances to ``diagnose`` the moment step 2 completes, so a
    case still at ``detect`` has been created but not acted on. Combined with
    the ``open`` status check, this is what stops a case being reassigned
    mid-recovery — after a message has already gone out.
    """
    if str(case.get("status") or "") != "open":
        return False
    return str(case.get("current_step") or "") in _UNTOUCHED_STEPS


def should_hold_out(case: dict[str, Any]) -> bool:
    """Whether this case becomes a control.

    Already-assigned cases short-circuit: re-running the loop over a holdout
    must not roll again and must not flip it back into treatment.
    """
    if case.get("is_holdout"):
        return True
    if not is_first_pass(case):
        return False
    return draw() < HOLDOUT_RATE


async def assign_holdout(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    context_features: dict[str, Any],
) -> None:
    """Mark the case as a control and record its frozen context.

    Both writes tolerate failure independently. If the ``uplift_holdouts`` row
    cannot be written the case is still flagged, which is the half that keeps
    the agent from contacting them — losing the row costs a training sample,
    losing the flag costs the experiment.
    """
    try:
        supabase_client.table("recovery_cases").update(
            {
                "is_holdout": True,
                "status": "holdout",
                "current_step": "detect",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", case_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("holdout_flag_error", case_id=case_id, error=str(exc))

    try:
        supabase_client.table("uplift_holdouts").upsert(
            {
                "case_id": case_id,
                "merchant_id": merchant_id,
                "assigned_at": datetime.now(UTC).isoformat(),
                "holdout_reason": f"random_{HOLDOUT_RATE:.0%}_control",
                "context_features": context_features,
                "used_in_training": False,
            },
            on_conflict="case_id",
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("holdout_row_error", case_id=case_id, error=str(exc))
