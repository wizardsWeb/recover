"""The uplift check as a gate.

The model can be right and the product still wrong, if the verdict does not
reach the loop. These tests are about that seam: which buckets stop a send,
which proceed, and what happens with no model at all.
"""

from typing import Any

import pytest

from app.agent.models import UpliftBucket
from app.agent.steps import uplift_check as step
from app.agent.steps.uplift_check import run_uplift_check

MERCHANT = "11111111-1111-4111-8111-111111111111"
PLAYBOOK = "subscription_failure"

CONTEXT = {
    "bank": "ICIC",
    "method": "UPI",
    "period": "morning",
    "ltv_bucket": "high",
    "tenure_bucket": "established",
    "amount_bucket": "medium",
    "has_salary_mismatch_pattern": False,
}


class _Client:
    """Stands in for Supabase — the snapshot fetch is mocked out above it."""


def pin(monkeypatch: pytest.MonkeyPatch, bucket: UpliftBucket, cate: float) -> None:
    """Force a prediction, with a snapshot present."""
    monkeypatch.setattr(step, "latest_snapshot", lambda *a, **k: {"bucket_uplifts": {}})
    monkeypatch.setattr(step, "predict_uplift_bucket", lambda *a, **k: (bucket, cate))


async def run(**overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "supabase_client": _Client(),
        "context_features": CONTEXT,
        "merchant_id": MERCHANT,
        "playbook": PLAYBOOK,
    }
    kwargs.update(overrides)
    return await run_uplift_check({}, {}, **kwargs)


# ── Which buckets stop a send ──────────────────────────────────────────


async def test_persuadable_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    pin(monkeypatch, UpliftBucket.PERSUADABLE, 0.31)
    verdict = await run()

    assert verdict.verdict == "PROCEED"
    assert verdict.bucket is UpliftBucket.PERSUADABLE
    assert verdict.estimated_lift == 0.31
    assert verdict.is_stub is False


async def test_sure_thing_proceeds_because_the_message_is_nearly_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The honesty owed here is about attribution, not about acting.

    Skipping sure things would forgo real recoveries to protect a number. The
    ROI page handles it instead, by not counting them as caused.
    """
    pin(monkeypatch, UpliftBucket.SURE_THING, 0.04)
    verdict = await run()

    assert verdict.verdict == "PROCEED"
    assert "not counted as caused" in verdict.reasoning


async def test_lost_cause_skips(monkeypatch: pytest.MonkeyPatch) -> None:
    pin(monkeypatch, UpliftBucket.LOST_CAUSE, -0.02)
    assert (await run()).verdict == "SKIP"


async def test_do_not_disturb_skips_and_says_contact_is_the_harm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bucket the holdout group exists to make visible."""
    pin(monkeypatch, UpliftBucket.DO_NOT_DISTURB, -0.28)
    verdict = await run()

    assert verdict.verdict == "SKIP"
    assert verdict.estimated_lift == -0.28
    assert "drives them away" in verdict.reasoning


# ── No model ───────────────────────────────────────────────────────────


async def test_no_snapshot_proceeds_rather_than_going_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A merchant in week one must still get a working agent.

    If an unmeasurable case defaulted to SKIP, a new deployment would recover
    nothing and look, from the outside, exactly like a functioning one.
    """
    monkeypatch.setattr(step, "latest_snapshot", lambda *a, **k: None)
    verdict = await run()

    assert verdict.verdict == "PROCEED"
    assert verdict.bucket is UpliftBucket.UNKNOWN
    assert verdict.is_stub is True


async def test_a_call_without_context_degrades_to_proceed() -> None:
    """Callers that never extracted a vector get the pre-Phase-9 behaviour."""
    verdict = await run_uplift_check({}, {})

    assert verdict.verdict == "PROCEED"
    assert verdict.bucket is UpliftBucket.UNKNOWN
    assert verdict.is_stub is True


async def test_a_real_prediction_is_not_flagged_as_a_stub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`is_stub` drives the UI's provenance badge — it must track the snapshot."""
    pin(monkeypatch, UpliftBucket.PERSUADABLE, 0.2)
    assert (await run()).is_stub is False

    monkeypatch.setattr(step, "latest_snapshot", lambda *a, **k: None)
    assert (await run()).is_stub is True
