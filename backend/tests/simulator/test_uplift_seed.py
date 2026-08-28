"""The seeded uplift corpus.

A seeder is easy to write and easy to get quietly wrong: the rows land, the
training call returns 200, and the model has learned from scrambled labels or
from a control group that was never big enough to say anything. The tests here
are the properties that separate those two outcomes.

The end-to-end assertion — that a T-learner fitted on this corpus recovers the
effects the corpus was drawn with — is the one worth having. It fails if the
segments stop carrying feature signal, if treated and control features stop
being built the same way, or if the labels ever get zipped onto the wrong case.
"""

from typing import Any

import pytest

from app.ml.uplift.model import MIN_GROUP_SAMPLES, predict_uplift_bucket, train_uplift_model
from app.simulator.uplift_seed import (
    MIN_CONTROLS_PER_PLAYBOOK,
    PLAYBOOK_WEIGHTS,
    SEGMENTS,
    _allocate,
    seed_uplift_history,
)
from tests.simulator.fake_supabase import FakeSupabase

MERCHANT = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT)
    return fake


def segment(bucket: str) -> Any:
    return next(s for s in SEGMENTS if s.bucket == bucket)


# ── Allocation ─────────────────────────────────────────────────────────


def test_every_playbook_clears_the_training_minimum() -> None:
    """The property the whole control floor exists for.

    `b2b_overdue` is a tenth of the volume. Left proportional it trains on four
    controls, returns `insufficient_data`, and the ROI page shows three buckets
    and a shrug — for a reason nothing in the response explains.
    """
    for treated, controls in _allocate(320, 0.25).values():
        assert controls >= MIN_CONTROLS_PER_PLAYBOOK
        assert controls > MIN_GROUP_SAMPLES
        assert treated >= MIN_GROUP_SAMPLES


def test_the_floor_holds_at_the_smallest_allowed_corpus() -> None:
    """40 cases is the endpoint's lower bound; it must still produce a model."""
    for _, controls in _allocate(40, 0.25).values():
        assert controls >= MIN_CONTROLS_PER_PLAYBOOK


def test_volume_still_follows_the_playbook_mix_once_the_floor_is_met() -> None:
    allocation = _allocate(2000, 0.25)
    totals = {name: sum(counts) for name, counts in allocation.items()}

    assert totals["subscription_failure"] > totals["checkout_abandonment"]
    assert totals["checkout_abandonment"] > totals["failed_payment"]
    assert totals["failed_payment"] > totals["b2b_overdue"]


# ── What lands in the database ─────────────────────────────────────────


def test_treated_and_control_rows_go_to_the_tables_training_reads(db: FakeSupabase) -> None:
    """Features live in two different places, and training reads both.

    Treated context comes from `agent_decisions.bandit_context_vector`; control
    context from `uplift_holdouts.context_features`. A seeder that wrote only
    case rows would insert 320 rows, return success, and train on nothing.
    """
    summary = seed_uplift_history(db, MERCHANT, total_cases=320, seed=7)

    cases = db.rows("recovery_cases")
    assert len(cases) == summary["cases"]
    assert len(db.rows("agent_decisions")) == summary["treated"]
    assert len(db.rows("uplift_holdouts")) == summary["controls"]

    holdout_ids = {row["case_id"] for row in db.rows("uplift_holdouts")}
    decision_ids = {row["case_id"] for row in db.rows("agent_decisions")}
    # No case is in both arms — that would be a customer counted as its own
    # control, and the measured effect would be zero by construction.
    assert holdout_ids.isdisjoint(decision_ids)
    assert {c["id"] for c in cases if c["is_holdout"]} == holdout_ids


def test_a_control_is_never_left_looking_like_a_failure(db: FakeSupabase) -> None:
    """A recovered control recovered money, and the case row has to say so.

    If controls were left at zero recovered, every comparison against them would
    overstate the agent's effect — the exact number the page exists to be honest
    about.
    """
    seed_uplift_history(db, MERCHANT, total_cases=320, seed=7)

    recovered_controls = [
        row for row in db.rows("uplift_holdouts") if row["outcome"] == "recovered"
    ]
    assert recovered_controls, "a control group that never recovers is not a control group"

    by_id = {row["id"]: row for row in db.rows("recovery_cases")}
    for holdout in recovered_controls:
        case = by_id[holdout["case_id"]]
        assert case["amount_recovered_cents"] > 0
        assert case["amount_recovered_cents"] == holdout["outcome_amount_cents"]
        # Still identifiable as a control from the case table alone.
        assert case["status"] == "holdout"


def test_a_case_points_at_a_customer_whose_ltv_matches_its_context(db: FakeSupabase) -> None:
    """The context vector is derived from the customer in the live loop.

    Seeding a high-LTV context onto a low-LTV customer leaves the two
    disagreeing the moment anything recomputes the vector.
    """
    seed_uplift_history(db, MERCHANT, total_cases=120, seed=3)

    customers = {row["id"]: row for row in db.rows("customers")}
    cases = {row["id"]: row for row in db.rows("recovery_cases")}
    for decision in db.rows("agent_decisions"):
        context = decision["bandit_context_vector"]
        customer = customers[cases[decision["case_id"]]["customer_id"]]
        assert customer["external_id"].split("-")[2] == context["ltv_bucket"]
        assert customer["external_id"].split("-")[3] == context["tenure_bucket"]


def test_reseeding_does_not_duplicate_the_customer_pool(db: FakeSupabase) -> None:
    """Seeding twice is the normal demo mistake; it must not fork the pool."""
    first = seed_uplift_history(db, MERCHANT, total_cases=80, seed=1)
    second = seed_uplift_history(db, MERCHANT, total_cases=80, seed=2)

    assert first["customers"] == second["customers"] == len(db.rows("customers"))


def test_a_fixed_seed_reproduces_the_corpus() -> None:
    """A demo that shows a different effect on every run cannot be rehearsed."""
    outcomes = []
    for _ in range(2):
        fresh = FakeSupabase()
        fresh.seed_merchant(MERCHANT)
        seed_uplift_history(fresh, MERCHANT, total_cases=120, seed=42)
        outcomes.append(
            [
                (row["playbook"], row["status"], row["amount_at_risk_cents"])
                for row in fresh.rows("recovery_cases")
            ]
        )

    assert outcomes[0] == outcomes[1]


# ── The corpus teaches what it was drawn with ──────────────────────────


def test_the_model_recovers_the_effects_the_corpus_was_drawn_with(db: FakeSupabase) -> None:
    """The assertion that makes the rest of the file worth keeping.

    Every playbook trains, and the fitted T-learner separates a segment contact
    helps from one contact harms. That fails if the segments stop carrying
    feature signal, if treated and control features stop being encoded the same
    way, or if a label ever gets zipped onto the wrong case.
    """
    seed_uplift_history(db, MERCHANT, total_cases=600, seed=11)

    results = {
        playbook: train_uplift_model(db, MERCHANT, playbook) for playbook in PLAYBOOK_WEIGHTS
    }
    assert {r["status"] for r in results.values()} == {"trained"}
    assert len(db.rows("uplift_model_snapshots")) == len(PLAYBOOK_WEIGHTS)

    snapshot = db.rows("uplift_model_snapshots")[0]
    persuadable = segment("persuadable")
    harmful = segment("dnd")

    _, helped = predict_uplift_bucket(
        {
            "bank": "HDFC",
            "method": persuadable.methods[0],
            "period": persuadable.periods[0],
            "ltv_bucket": persuadable.ltv_buckets[-1],
            "tenure_bucket": persuadable.tenure_buckets[-1],
            "amount_bucket": persuadable.amount_buckets[0],
            "has_salary_mismatch_pattern": False,
        },
        snapshot,
    )
    _, hurt = predict_uplift_bucket(
        {
            "bank": "HDFC",
            "method": harmful.methods[0],
            "period": harmful.periods[0],
            "ltv_bucket": harmful.ltv_buckets[0],
            "tenure_bucket": harmful.tenure_buckets[0],
            "amount_bucket": harmful.amount_buckets[0],
            "has_salary_mismatch_pattern": True,
        },
        snapshot,
    )

    assert helped > hurt
    assert helped > 0.0
    assert hurt < helped - 0.2


def test_an_unseen_bank_does_not_move_the_estimate(db: FakeSupabase) -> None:
    """Bank is the noise dimension — the model should find nothing in it.

    It is also the field most likely to arrive as a value training never saw,
    which is the case the stored feature layout exists to survive.
    """
    seed_uplift_history(db, MERCHANT, total_cases=400, seed=5)
    train_uplift_model(db, MERCHANT, "subscription_failure")
    snapshot = db.rows("uplift_model_snapshots")[0]

    base = {
        "method": "UPI",
        "period": "morning",
        "ltv_bucket": "high",
        "tenure_bucket": "established",
        "amount_bucket": "medium",
        "has_salary_mismatch_pattern": False,
    }
    _, known = predict_uplift_bucket({**base, "bank": "HDFC"}, snapshot)
    _, unseen = predict_uplift_bucket({**base, "bank": "NEWB"}, snapshot)

    assert abs(known - unseen) < 0.15
