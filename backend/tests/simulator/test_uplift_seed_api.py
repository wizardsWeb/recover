"""The seed endpoint.

The generative logic is tested in `test_uplift_seed.py`; what is left here is
the endpoint's own contract — that it produces the finished state in one call,
that it is authenticated and dev-gated like the rest of the simulator, and that
its bounds hold.
"""

import pytest
from fastapi.testclient import TestClient

from app.deps import get_current_user_id, get_user_supabase
from app.main import app
from app.simulator.uplift_seed import MAX_TOTAL_CASES
from tests.simulator.conftest import MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase


def test_one_call_leaves_a_trained_model_for_every_playbook(
    client: TestClient, db: FakeSupabase
) -> None:
    """Corpus and model are one endpoint because neither is useful alone."""
    response = client.post("/api/simulator/uplift/seed", json={"totalCases": 400, "seed": 9})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cases"] == body["treated"] + body["controls"]
    assert {m["status"] for m in body["models"]} == {"trained"}
    assert len(db.rows("uplift_model_snapshots")) == 4


def test_the_response_reports_the_group_sizes_behind_each_model(client: TestClient) -> None:
    """A number on the ROI page is only as trustworthy as the n behind it."""
    body = client.post("/api/simulator/uplift/seed", json={"totalCases": 400, "seed": 9}).json()

    for model in body["models"]:
        assert model["controlSamples"] >= 10
        assert model["treatedSamples"] >= 10
        assert model["meanCate"] is not None


def test_seeding_writes_only_into_the_calling_merchant(
    client: TestClient, db: FakeSupabase
) -> None:
    """RLS enforces this in production; the query logic must not fight it."""
    client.post("/api/simulator/uplift/seed", json={"totalCases": 80, "seed": 1})

    assert {row["merchant_id"] for row in db.rows("recovery_cases")} == {MERCHANT_ID}
    assert {row["merchant_id"] for row in db.rows("uplift_holdouts")} == {MERCHANT_ID}


@pytest.mark.parametrize("total", [39, MAX_TOTAL_CASES + 1])
def test_an_out_of_range_corpus_is_rejected(client: TestClient, total: int) -> None:
    """A typo'd zero should cost a 422, not a hundred thousand rows."""
    response = client.post("/api/simulator/uplift/seed", json={"totalCases": total})

    assert response.status_code == 422


def test_the_endpoint_requires_authentication() -> None:
    with TestClient(app) as anonymous:
        response = anonymous.post("/api/simulator/uplift/seed", json={})
        assert response.status_code in (401, 403)


def test_the_endpoint_is_gone_outside_a_development_environment(
    monkeypatch: pytest.MonkeyPatch, db: FakeSupabase
) -> None:
    """Fabricating a recovery history into a real ledger is the thing to prevent."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    try:
        with TestClient(app) as production:
            assert production.post("/api/simulator/uplift/seed", json={}).status_code == 404
    finally:
        app.dependency_overrides.clear()
