"""Retrain scheduling.

The scheduler's job is to be invisible: refit when it is worth it, stay out of
the way otherwise, and never take the agent down with it. Each of those is a
property that fails quietly, so each is tested.
"""

from typing import Any

import pytest

from app.ml.uplift import training
from app.ml.uplift.training import (
    MIN_NEW_CASES_BETWEEN_TRAINING,
    maybe_retrain_uplift_model,
    schedule_retrain,
)
from tests.simulator.fake_supabase import FakeSupabase

MERCHANT = "11111111-1111-4111-8111-111111111111"
PLAYBOOK = "subscription_failure"


def seed_closed_cases(db: FakeSupabase, count: int) -> None:
    for index in range(count):
        db.rows("recovery_cases").append(
            {
                "id": f"case-{index}",
                "merchant_id": MERCHANT,
                "playbook": PLAYBOOK,
                "status": "recovered",
                "closed_at": "2026-08-01T00:00:00Z",
                "is_holdout": False,
            }
        )


def seed_snapshot(db: FakeSupabase, sample_size: int) -> None:
    db.rows("uplift_model_snapshots").append(
        {
            "id": "snap-1",
            "merchant_id": MERCHANT,
            "playbook": PLAYBOOK,
            "trained_at": "2026-08-01T00:00:00Z",
            "model_type": "t_learner",
            "training_sample_size": sample_size,
            "bucket_uplifts": {},
        }
    )


# ── The debounce ───────────────────────────────────────────────────────


async def test_no_snapshot_yet_always_trains(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSupabase()
    calls: list[str] = []
    monkeypatch.setattr(
        training, "train_uplift_model", lambda *a, **k: calls.append("trained") or {}
    )

    await maybe_retrain_uplift_model(db, MERCHANT, PLAYBOOK)

    assert calls == ["trained"]


async def test_too_few_new_cases_does_not_refit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refitting per case would spend its time re-deriving the same weights."""
    db = FakeSupabase()
    seed_snapshot(db, sample_size=100)
    seed_closed_cases(db, 100 + MIN_NEW_CASES_BETWEEN_TRAINING - 1)

    calls: list[str] = []
    monkeypatch.setattr(
        training, "train_uplift_model", lambda *a, **k: calls.append("trained") or {}
    )

    assert await maybe_retrain_uplift_model(db, MERCHANT, PLAYBOOK) is None
    assert calls == []


async def test_enough_new_cases_refits(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSupabase()
    seed_snapshot(db, sample_size=100)
    seed_closed_cases(db, 100 + MIN_NEW_CASES_BETWEEN_TRAINING)

    calls: list[str] = []
    monkeypatch.setattr(
        training, "train_uplift_model", lambda *a, **k: calls.append("trained") or {}
    )

    await maybe_retrain_uplift_model(db, MERCHANT, PLAYBOOK)
    assert calls == ["trained"]


async def test_staleness_counts_outcomes_not_elapsed_time() -> None:
    """A quiet week produces no new outcomes and needs no refit."""
    db = FakeSupabase()
    seed_snapshot(db, sample_size=50)
    seed_closed_cases(db, 50)

    assert training._should_retrain(db, MERCHANT, PLAYBOOK) is False


def test_open_cases_do_not_count_towards_staleness() -> None:
    """An unclosed case has no outcome to learn from."""
    db = FakeSupabase()
    seed_snapshot(db, sample_size=0)
    for index in range(50):
        db.rows("recovery_cases").append(
            {
                "id": f"open-{index}",
                "merchant_id": MERCHANT,
                "playbook": PLAYBOOK,
                "status": "in_flight",
                "closed_at": None,
                "is_holdout": False,
            }
        )

    assert training._closed_case_count(db, MERCHANT, PLAYBOOK) == 0


# ── Failure is contained ───────────────────────────────────────────────


async def test_a_training_failure_never_reaches_the_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recovery already happened; a reporting failure must not undo it."""

    def _explode(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("sklearn fell over")

    monkeypatch.setattr(training, "train_uplift_model", _explode)

    assert await maybe_retrain_uplift_model(FakeSupabase(), MERCHANT, PLAYBOOK) is None


def test_scheduling_outside_an_event_loop_is_a_no_op() -> None:
    """A synchronous caller has no loop to schedule into, and that is fine."""
    schedule_retrain(FakeSupabase(), MERCHANT, PLAYBOOK)


# ── The task is held ───────────────────────────────────────────────────


async def test_a_scheduled_task_is_strongly_referenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without this the loop holds only a weak reference.

    A fire-and-forget task nobody holds can be garbage-collected part-way
    through. It does not raise — it simply stops, and the snapshot never
    appears.
    """
    monkeypatch.setattr(training, "train_uplift_model", lambda *a, **k: {})

    schedule_retrain(FakeSupabase(), MERCHANT, PLAYBOOK)
    assert len(training._IN_FLIGHT) == 1

    # And releases it once done, so the set is not an unbounded leak.
    task = next(iter(training._IN_FLIGHT))
    await task
    assert set() == training._IN_FLIGHT
