"""The T-learner.

An uplift model that is wrong does not crash — it returns a number, and the ROI
page renders it. So the tests here are about the failure modes that produce
plausible output: a feature layout that shifts between training and prediction,
a group too small to mean anything, and a segment boundary that puts a harmful
contact in the "send it" bucket.
"""

from typing import Any

import numpy as np

from app.agent.models import UpliftBucket
from app.ml.uplift.model import (
    MIN_GROUP_SAMPLES,
    bucket_for_cate,
    build_feature_matrix,
    predict_uplift_bucket,
    train_uplift_model,
)
from tests.simulator.fake_supabase import FakeSupabase

MERCHANT = "11111111-1111-4111-8111-111111111111"
PLAYBOOK = "subscription_failure"


def context(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "bank": "ICIC",
        "method": "UPI",
        "period": "morning",
        "ltv_bucket": "high",
        "tenure_bucket": "established",
        "amount_bucket": "medium",
        "has_salary_mismatch_pattern": False,
    }
    base.update(overrides)
    return base


# ── Segment boundaries ─────────────────────────────────────────────────


def test_the_bucket_boundaries_are_where_the_product_says_they_are() -> None:
    assert bucket_for_cate(0.40) is UpliftBucket.PERSUADABLE
    assert bucket_for_cate(0.16) is UpliftBucket.PERSUADABLE
    assert bucket_for_cate(0.15) is UpliftBucket.SURE_THING  # strict >
    assert bucket_for_cate(0.01) is UpliftBucket.SURE_THING
    assert bucket_for_cate(0.0) is UpliftBucket.LOST_CAUSE
    assert bucket_for_cate(-0.09) is UpliftBucket.LOST_CAUSE
    assert bucket_for_cate(-0.1) is UpliftBucket.DO_NOT_DISTURB
    assert bucket_for_cate(-0.5) is UpliftBucket.DO_NOT_DISTURB


def test_a_harmful_effect_is_never_bucketed_as_worth_sending() -> None:
    """The one misclassification with a victim attached."""
    for cate in (-0.001, -0.05, -0.2, -0.9):
        assert bucket_for_cate(cate) in {UpliftBucket.LOST_CAUSE, UpliftBucket.DO_NOT_DISTURB}


# ── Feature encoding ───────────────────────────────────────────────────


def test_the_column_layout_is_stable_across_input_order() -> None:
    """Insertion-ordered columns would make a snapshot's weights meaningless."""
    first = [context(bank="HDFC"), context(bank="ICIC"), context(bank="SBI")]
    second = [context(bank="SBI"), context(bank="HDFC"), context(bank="ICIC")]

    _, names_a = build_feature_matrix(first)
    _, names_b = build_feature_matrix(second)

    assert names_a == names_b


def test_an_unseen_category_encodes_as_absent_not_as_a_shift() -> None:
    """The property that protects a live prediction from a new bank.

    Without a stored layout, a bank the model has never seen would add a column
    and move every later feature one place right — the weights would still
    multiply, and the answer would be silently meaningless.
    """
    _, names = build_feature_matrix([context(bank="ICIC")])
    matrix, used = build_feature_matrix([context(bank="NEWB")], names)

    assert used == names
    assert matrix.shape[1] == len(names)
    # Nothing in the bank group fires; the rest of the row is unaffected.
    bank_columns = [i for i, name in enumerate(names) if name.startswith("bank=")]
    assert matrix[0, bank_columns].sum() == 0.0
    assert matrix[0, names.index("period=morning")] == 1.0


def test_a_missing_field_encodes_as_unknown_rather_than_crashing() -> None:
    matrix, names = build_feature_matrix([{"bank": "ICIC"}])
    assert "period=unknown" in names
    assert matrix[0, names.index("period=unknown")] == 1.0


def test_a_boolean_feature_is_one_column() -> None:
    matrix, names = build_feature_matrix(
        [context(has_salary_mismatch_pattern=True), context(has_salary_mismatch_pattern=False)]
    )
    column = names.index("has_salary_mismatch_pattern")
    assert matrix[0, column] == 1.0
    assert matrix[1, column] == 0.0


# ── Training refuses to speak without evidence ─────────────────────────


def seed(db: FakeSupabase, treated: int, control: int, *, treated_win: float = 0.7) -> None:
    """Seed closed cases and resolved holdouts directly into the fake."""
    for index in range(treated):
        case_id = f"treated-{index}"
        recovered = index < int(treated * treated_win)
        db.rows("recovery_cases").append(
            {
                "id": case_id,
                "merchant_id": MERCHANT,
                "playbook": PLAYBOOK,
                "status": "recovered" if recovered else "stopped",
                "is_holdout": False,
                "closed_at": "2026-08-01T00:00:00Z",
                "amount_recovered_cents": 100000 if recovered else 0,
                "uplift_bucket": None,
            }
        )
        db.rows("agent_decisions").append(
            {
                "case_id": case_id,
                "merchant_id": MERCHANT,
                "bandit_context_vector": context(
                    period="morning" if index % 2 else "evening",
                    ltv_bucket="high" if index % 3 else "low",
                ),
            }
        )
    for index in range(control):
        case_id = f"control-{index}"
        recovered = index < max(1, int(control * 0.2))
        db.rows("recovery_cases").append(
            {
                "id": case_id,
                "merchant_id": MERCHANT,
                "playbook": PLAYBOOK,
                "status": "holdout",
                "is_holdout": True,
                "closed_at": "2026-08-01T00:00:00Z",
                "amount_recovered_cents": 100000 if recovered else 0,
                "uplift_bucket": None,
            }
        )
        db.rows("uplift_holdouts").append(
            {
                "case_id": case_id,
                "merchant_id": MERCHANT,
                "outcome": "recovered" if recovered else "not_recovered",
                "outcome_amount_cents": 100000 if recovered else 0,
                "context_features": context(
                    period="morning" if index % 2 else "evening",
                    ltv_bucket="high" if index % 3 else "low",
                ),
            }
        )


def test_too_few_controls_returns_insufficient_data_rather_than_a_number() -> None:
    db = FakeSupabase()
    seed(db, treated=40, control=3)

    result = train_uplift_model(db, MERCHANT, PLAYBOOK)

    assert result["status"] == "insufficient_data"
    assert result["min_samples"] == MIN_GROUP_SAMPLES
    assert result["control_samples"] == 3
    assert db.rows("uplift_model_snapshots") == []


def test_too_few_treated_also_refuses() -> None:
    db = FakeSupabase()
    seed(db, treated=4, control=30)

    assert train_uplift_model(db, MERCHANT, PLAYBOOK)["status"] == "insufficient_data"


def test_unresolved_holdouts_do_not_count_towards_the_minimum() -> None:
    """An assigned control with no observed outcome teaches nothing."""
    db = FakeSupabase()
    seed(db, treated=40, control=20)
    for row in db.rows("uplift_holdouts"):
        row["outcome"] = None

    assert train_uplift_model(db, MERCHANT, PLAYBOOK)["control_samples"] == 0


# ── A trained model ────────────────────────────────────────────────────


def test_training_produces_a_snapshot_with_json_coefficients() -> None:
    db = FakeSupabase()
    seed(db, treated=60, control=30)

    result = train_uplift_model(db, MERCHANT, PLAYBOOK)

    assert result["status"] == "trained"
    assert result["model_type"] == "t_learner"
    # No pickled estimator — everything needed to predict is plain JSON.
    assert isinstance(result["treated"]["coef"], list)
    assert all(isinstance(w, float) for w in result["treated"]["coef"])
    assert len(result["treated"]["coef"]) == len(result["feature_names"])

    snapshots = db.rows("uplift_model_snapshots")
    assert len(snapshots) == 1
    assert snapshots[0]["training_sample_size"] == 90


def test_a_treated_group_that_beats_control_yields_positive_average_uplift() -> None:
    """70% treated against 20% control should read as the agent helping."""
    db = FakeSupabase()
    seed(db, treated=60, control=30, treated_win=0.7)

    result = train_uplift_model(db, MERCHANT, PLAYBOOK)

    assert result["treated_recovery_rate"] > result["control_recovery_rate"]
    assert result["mean_cate"] > 0


def test_prediction_round_trips_through_the_stored_snapshot() -> None:
    db = FakeSupabase()
    seed(db, treated=60, control=30)
    train_uplift_model(db, MERCHANT, PLAYBOOK)

    snapshot = db.rows("uplift_model_snapshots")[0]
    bucket, cate = predict_uplift_bucket(context(), snapshot)

    assert bucket is not UpliftBucket.UNKNOWN
    assert -1.0 <= cate <= 1.0


def test_no_snapshot_predicts_unknown_not_do_not_disturb() -> None:
    """The failure mode matters.

    UNKNOWN means proceed. If an untrained merchant defaulted to the bottom
    bucket, the agent would go silent on every case and report it as caution.
    """
    bucket, cate = predict_uplift_bucket(context(), None)

    assert bucket is UpliftBucket.UNKNOWN
    assert cate == 0.0


def test_a_malformed_snapshot_predicts_unknown() -> None:
    assert predict_uplift_bucket(context(), {"bucket_uplifts": {}})[0] is UpliftBucket.UNKNOWN
    assert (
        predict_uplift_bucket(context(), {"bucket_uplifts": {"feature_names": ["a"]}})[0]
        is UpliftBucket.UNKNOWN
    )


def test_a_single_class_group_degrades_to_a_constant_rather_than_raising() -> None:
    """Every control failing is a real early state, not a bug."""
    db = FakeSupabase()
    seed(db, treated=60, control=30)
    for row in db.rows("uplift_holdouts"):
        row["outcome"] = "not_recovered"

    result = train_uplift_model(db, MERCHANT, PLAYBOOK)

    assert result["status"] == "trained"
    assert result["control_recovery_rate"] == 0.0
    # A control group that never recovers makes contact look maximally
    # effective, which is exactly what the data says.
    assert result["mean_cate"] > 0
    assert not np.isnan(result["mean_cate"])
