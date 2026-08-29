"""Keeping a simulation out of the numbers that describe reality.

A batch run writes a thousand `recovery_cases` rows with invented outcomes. Every
read that reports money has to exclude them, and the failure mode if one does not
is the worst this product could have: a fabricated figure rendered in rupees,
beside real ones, with nothing to distinguish it.

The flag is checked with `is.null` rather than `neq.true`, because PostgREST
inherits SQL's three-valued logic and `neq` drops rows where the key is absent —
which is every real case. A filter written that way excludes exactly the rows it
exists to keep, and the page goes blank instead of wrong. These tests would catch
either.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import network as network_module
from app.deps import get_current_user_id, get_user_supabase
from app.main import app
from app.ml.uplift.model import _treated_samples
from tests.simulator.conftest import MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase

TODAY = "2026-08-29T06:00:00+00:00"


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    return fake


@pytest.fixture
def client(db: FakeSupabase) -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def add_case(
    db: FakeSupabase,
    *,
    synthetic: bool,
    recovered: bool = True,
    amount: int = 100_000,
    playbook: str = "subscription_failure",
) -> str:
    from datetime import UTC, datetime

    case_id = f"case-{len(db.rows('recovery_cases'))}"
    now = datetime.now(UTC).isoformat()
    db.rows("recovery_cases").append(
        {
            "id": case_id,
            "merchant_id": MERCHANT_ID,
            "playbook": playbook,
            "status": "recovered" if recovered else "stopped",
            "amount_at_risk_cents": amount,
            "amount_recovered_cents": amount if recovered else 0,
            "opened_at": now,
            "closed_at": now,
            "is_holdout": False,
            "uplift_bucket": None,
            "metadata": {"is_batch_synthetic": True} if synthetic else {},
        }
    )
    return case_id


def test_the_dashboard_kpis_ignore_simulated_cases(client: TestClient, db: FakeSupabase) -> None:
    """Four tiles reporting a simulation as today's revenue."""
    add_case(db, synthetic=False, amount=50_000)
    for _ in range(50):
        add_case(db, synthetic=True, amount=1_000_000)

    body = client.get("/api/analytics/overview").json()

    assert body["cases_opened_today"] == 1
    assert body["amount_recovered_today_cents"] == 50_000


def test_the_roi_page_ignores_simulated_cases(client: TestClient, db: FakeSupabase) -> None:
    """The page whose entire purpose is an honest attribution number."""
    add_case(db, synthetic=False, amount=50_000)
    for _ in range(50):
        add_case(db, synthetic=True, amount=1_000_000)

    body = client.get("/api/analytics/uplift").json()

    assert body["gross_recovery_cents"] == 50_000
    assert body["holdout_stats"]["treated_cases"] == 1


def test_the_network_benchmark_ignores_simulated_cases(
    client: TestClient, db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise a merchant who ran a demo jumps the percentile on invented wins."""
    monkeypatch.setattr(network_module, "get_service_client", lambda: db)
    add_case(db, synthetic=False, recovered=False)
    for _ in range(50):
        add_case(db, synthetic=True, recovered=True)

    assert client.get("/api/network/benchmark").json()["merchant_rate"] == 0.0


def test_uplift_training_ignores_simulated_cases(db: FakeSupabase) -> None:
    """A model fitted on a simulation, then used to decide whether to contact
    actual customers, is the quietest version of this failure."""
    real = add_case(db, synthetic=False)
    synthetic = add_case(db, synthetic=True)
    for case_id in (real, synthetic):
        db.rows("agent_decisions").append(
            {
                "case_id": case_id,
                "merchant_id": MERCHANT_ID,
                "bandit_context_vector": {"bank": "HDFC", "method": "UPI"},
            }
        )

    samples = _treated_samples(db, MERCHANT_ID, "subscription_failure")

    assert len(samples) == 1


def test_the_case_list_hides_simulated_cases_by_default(
    client: TestClient, db: FakeSupabase
) -> None:
    """A thousand-case run would bury every real case below a page of them."""
    add_case(db, synthetic=False)
    for _ in range(20):
        add_case(db, synthetic=True)

    assert len(client.get("/api/cases").json()["cases"]) == 1


def test_the_case_list_can_be_asked_for_them(client: TestClient, db: FakeSupabase) -> None:
    """Hidden by default is not the same as unreachable — a batch run's cases
    are still the record of what it did."""
    add_case(db, synthetic=False)
    for _ in range(20):
        add_case(db, synthetic=True)

    body = client.get("/api/cases", params={"includeSynthetic": "true"}).json()

    assert len(body["cases"]) == 21


def test_a_real_case_with_empty_metadata_is_never_filtered_out(
    client: TestClient, db: FakeSupabase
) -> None:
    """The `neq.true` mistake, caught directly.

    Under SQL's three-valued logic `neq` drops rows where the key is absent —
    every real case — so the filter would exclude precisely what it exists to
    keep, and every money figure on the product would read zero.
    """
    for _ in range(5):
        add_case(db, synthetic=False, amount=10_000)

    body = client.get("/api/analytics/overview").json()

    assert body["cases_opened_today"] == 5
    assert body["amount_recovered_today_cents"] == 50_000
