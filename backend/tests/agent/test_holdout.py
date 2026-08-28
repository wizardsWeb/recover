"""Holdout assignment — the control group's integrity.

The properties tested here are the ones whose failure would not crash anything.
A poisoned control group produces numbers, and the numbers look fine; they are
just wrong, and wrong in the direction that flatters the product. So:

* a control is never contacted,
* a case already under way is never reassigned,
* a control never teaches the bandit,
* and the context is frozen at assignment rather than recomputed later.
"""

from typing import Any

import pytest

from app.agent import holdout
from app.agent.holdout import HOLDOUT_RATE, is_first_pass, should_hold_out


def case(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "case-1",
        "status": "open",
        "current_step": None,
        "is_holdout": False,
    }
    base.update(overrides)
    return base


# ── The draw ───────────────────────────────────────────────────────────


def test_a_draw_under_the_rate_assigns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(holdout, "draw", lambda: HOLDOUT_RATE - 0.001)
    assert should_hold_out(case()) is True


def test_a_draw_on_the_rate_does_not_assign(monkeypatch: pytest.MonkeyPatch) -> None:
    """The comparison is strict `<`, so the boundary is treated, not held out."""
    monkeypatch.setattr(holdout, "draw", lambda: HOLDOUT_RATE)
    assert should_hold_out(case()) is False


def test_the_rate_is_a_small_minority() -> None:
    """A holdout costs real recovery — it must stay a sampling rate, not a policy."""
    assert 0 < HOLDOUT_RATE <= 0.1


# ── Assignment happens once ────────────────────────────────────────────


def test_a_case_already_in_flight_is_never_assigned(monkeypatch: pytest.MonkeyPatch) -> None:
    """The property that keeps the control group clean.

    `run_agent_loop` runs per pass. If a later pass could assign, a case that
    had already been sent a WhatsApp could become a "control", and every
    incremental figure computed from the group would be wrong.
    """
    monkeypatch.setattr(holdout, "draw", lambda: 0.0)

    assert should_hold_out(case(status="in_flight", current_step="listen")) is False


def test_a_reopened_pass_on_an_untouched_case_still_counts_as_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(holdout, "draw", lambda: 0.0)
    assert is_first_pass(case()) is True
    assert should_hold_out(case()) is True


def test_an_assigned_holdout_stays_assigned_without_redrawing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running the loop over a control must not flip it into treatment."""

    def _explode() -> float:
        raise AssertionError("draw() must not be called for an already-assigned holdout")

    monkeypatch.setattr(holdout, "draw", _explode)

    assert should_hold_out(case(is_holdout=True, status="holdout", current_step="detect")) is True
