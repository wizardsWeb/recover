"""The ROI endpoint.

This is the one place in the product that puts a rupee figure on "what did the
agent earn?". A number here that is merely plausible is worse than no number,
because nothing downstream can tell the difference — so the tests are mostly
about what the endpoint refuses to say.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import get_current_user_id, get_user_supabase
from app.main import app
from tests.simulator.conftest import MERCHANT_ID, OTHER_MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    fake.seed_merchant(OTHER_MERCHANT_ID)
    return fake


@pytest.fixture
def client(db: FakeSupabase) -> Any:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def add_case(
    db: FakeSupabase,
    *,
    case_id: str,
    bucket: str | None,
    recovered: bool,
    is_holdout: bool = False,
    amount: int = 100_000,
    playbook: str = "subscription_failure",
    merchant: str = MERCHANT_ID,
    outcome: str | None = None,
) -> None:
    status = "holdout" if is_holdout else ("recovered" if recovered else "stopped")
    db.rows("recovery_cases").append(
        {
            "id": case_id,
            "merchant_id": merchant,
            "playbook": playbook,
            "status": status,
            "uplift_bucket": bucket,
            "is_holdout": is_holdout,
            "amount_at_risk_cents": amount,
            "amount_recovered_cents": amount if recovered else 0,
            "closed_at": "2026-08-01T00:00:00Z",
        }
    )
    if is_holdout:
        db.rows("uplift_holdouts").append(
            {
                "case_id": case_id,
                "merchant_id": merchant,
                "outcome": outcome or ("recovered" if recovered else "not_recovered"),
                "outcome_amount_cents": amount if recovered else 0,
            }
        )


def seed_treated(db: FakeSupabase, bucket: str, *, recovered: int, stopped: int) -> None:
    for index in range(recovered):
        add_case(db, case_id=f"{bucket}-win-{index}", bucket=bucket, recovered=True)
    for index in range(stopped):
        add_case(db, case_id=f"{bucket}-loss-{index}", bucket=bucket, recovered=False)


def seed_controls(db: FakeSupabase, *, recovered: int, not_recovered: int) -> None:
    for index in range(recovered):
        add_case(db, case_id=f"ctl-win-{index}", bucket=None, recovered=True, is_holdout=True)
    for index in range(not_recovered):
        add_case(db, case_id=f"ctl-loss-{index}", bucket=None, recovered=False, is_holdout=True)


# ── What it refuses to say ─────────────────────────────────────────────


def test_with_no_controls_incremental_is_null_not_zero_and_not_gross(
    client: TestClient, db: FakeSupabase
) -> None:
    """The failure mode this endpoint exists to avoid.

    Without a control group there is nothing to subtract, and any number here
    would be a guess wearing a rupee sign. `null` plus `is_estimable: false` is
    a state the UI can render honestly; `0` and `gross` are both lies.
    """
    seed_treated(db, "persuadable", recovered=8, stopped=2)

    body = client.get("/api/analytics/uplift").json()

    assert body["gross_recovery_cents"] == 800_000
    assert body["incremental_recovery_cents"] is None
    assert body["incremental_pct_of_gross"] is None
    assert body["is_estimable"] is False
    assert "cannot be estimated" in body["methodology_note"]


def test_an_unresolved_control_is_not_counted_as_a_failure_to_recover(
    client: TestClient, db: FakeSupabase
) -> None:
    """An assigned control nobody has resolved teaches nothing.

    Counting it in the denominator drags the control rate down, and every rupee
    of the difference gets credited to the agent.
    """
    seed_treated(db, "persuadable", recovered=8, stopped=2)
    seed_controls(db, recovered=2, not_recovered=8)
    for index in range(20):
        add_case(
            db,
            case_id=f"pending-{index}",
            bucket=None,
            recovered=False,
            is_holdout=True,
            outcome="unknown",
        )

    body = client.get("/api/analytics/uplift").json()

    assert body["holdout_stats"]["resolved_controls"] == 10
    assert body["holdout_stats"]["control_recovery_rate"] == 0.2


def test_open_cases_do_not_dilute_the_rates(client: TestClient, db: FakeSupabase) -> None:
    seed_treated(db, "persuadable", recovered=8, stopped=2)
    seed_controls(db, recovered=2, not_recovered=8)
    db.rows("recovery_cases").append(
        {
            "id": "open-1",
            "merchant_id": MERCHANT_ID,
            "playbook": "subscription_failure",
            "status": "in_flight",
            "uplift_bucket": None,
            "is_holdout": False,
            "amount_at_risk_cents": 500_000,
            "amount_recovered_cents": 0,
            "closed_at": None,
        }
    )

    body = client.get("/api/analytics/uplift").json()

    assert body["holdout_stats"]["treated_cases"] == 10
    assert body["holdout_stats"]["treated_recovery_rate"] == 0.8


# ── Attribution ────────────────────────────────────────────────────────


def test_a_sure_thing_recovery_is_gross_but_barely_incremental(
    client: TestClient, db: FakeSupabase
) -> None:
    """The claim the whole page rests on.

    These customers were messaged and they paid, so the money is real and gross
    counts all of it. They would have paid anyway, so almost none of it was
    caused — which is exactly the correction the loop declines to make by
    skipping the send.
    """
    seed_treated(db, "sure_thing", recovered=9, stopped=1)
    seed_controls(db, recovered=8, not_recovered=2)

    body = client.get("/api/analytics/uplift").json()
    bucket = next(b for b in body["bucket_breakdown"] if b["bucket"] == "sure_thing")

    assert bucket["gross_recovery_cents"] == 900_000
    assert bucket["estimated_lift"] == pytest.approx(0.1, abs=0.001)
    assert bucket["incremental_recovery_cents"] < bucket["gross_recovery_cents"] * 0.2
    assert body["incremental_pct_of_gross"] < 0.2


def test_a_persuadable_recovery_is_credited_almost_in_full(
    client: TestClient, db: FakeSupabase
) -> None:
    seed_treated(db, "persuadable", recovered=9, stopped=1)
    seed_controls(db, recovered=1, not_recovered=9)

    body = client.get("/api/analytics/uplift").json()
    bucket = next(b for b in body["bucket_breakdown"] if b["bucket"] == "persuadable")

    assert bucket["estimated_lift"] == pytest.approx(0.8, abs=0.001)
    assert bucket["incremental_recovery_cents"] == pytest.approx(800_000, rel=0.01)


def test_a_bucket_where_contact_hurt_subtracts_rather_than_being_clamped(
    client: TestClient, db: FakeSupabase
) -> None:
    """A negative contribution is the finding, not an error to hide.

    Clamping it at zero would make the agent's total look better precisely
    where it was doing damage — the one place the number must not flatter.
    """
    seed_treated(db, "dnd", recovered=2, stopped=8)
    seed_controls(db, recovered=6, not_recovered=4)

    body = client.get("/api/analytics/uplift").json()
    bucket = next(b for b in body["bucket_breakdown"] if b["bucket"] == "dnd")

    assert bucket["estimated_lift"] < 0
    assert bucket["incremental_recovery_cents"] < 0
    assert body["incremental_recovery_cents"] < 0


def test_incremental_never_silently_exceeds_gross(client: TestClient, db: FakeSupabase) -> None:
    """Lift is bounded by the treated rate, so the scaled figure is bounded by gross."""
    seed_treated(db, "persuadable", recovered=10, stopped=0)
    seed_controls(db, recovered=0, not_recovered=10)

    body = client.get("/api/analytics/uplift").json()

    assert body["incremental_recovery_cents"] <= body["gross_recovery_cents"]
    assert body["incremental_pct_of_gross"] == 1.0


def test_a_bucket_with_its_own_controls_uses_them(client: TestClient, db: FakeSupabase) -> None:
    """A per-bucket rate beats the global one wherever there is enough of it."""
    seed_treated(db, "persuadable", recovered=9, stopped=1)
    seed_controls(db, recovered=5, not_recovered=5)
    for index in range(4):
        add_case(
            db,
            case_id=f"pctl-{index}",
            bucket="persuadable",
            recovered=index < 1,
            is_holdout=True,
        )

    body = client.get("/api/analytics/uplift").json()
    bucket = next(b for b in body["bucket_breakdown"] if b["bucket"] == "persuadable")

    assert bucket["uses_global_control_rate"] is False
    assert bucket["control_cases"] == 4
    assert bucket["control_recovery_rate"] == 0.25


# ── Scoping ────────────────────────────────────────────────────────────


def test_another_merchants_recoveries_are_not_in_the_total(
    client: TestClient, db: FakeSupabase
) -> None:
    seed_treated(db, "persuadable", recovered=8, stopped=2)
    seed_controls(db, recovered=2, not_recovered=8)
    add_case(
        db,
        case_id="other-1",
        bucket="persuadable",
        recovered=True,
        amount=99_000_000,
        merchant=OTHER_MERCHANT_ID,
    )

    body = client.get("/api/analytics/uplift").json()

    assert body["gross_recovery_cents"] == 800_000


def test_the_playbook_filter_narrows_the_estimate(client: TestClient, db: FakeSupabase) -> None:
    seed_treated(db, "persuadable", recovered=8, stopped=2)
    seed_controls(db, recovered=2, not_recovered=8)
    add_case(
        db,
        case_id="b2b-1",
        bucket="persuadable",
        recovered=True,
        amount=5_000_000,
        playbook="b2b_overdue",
    )

    everything = client.get("/api/analytics/uplift").json()
    subscription = client.get(
        "/api/analytics/uplift", params={"playbook": "subscription_failure"}
    ).json()

    assert everything["gross_recovery_cents"] == 5_800_000
    assert subscription["gross_recovery_cents"] == 800_000


def test_the_endpoint_requires_authentication() -> None:
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/analytics/uplift").status_code in (401, 403)
