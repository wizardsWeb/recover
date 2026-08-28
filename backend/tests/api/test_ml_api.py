"""The manual training endpoint.

It exists for the demo — the loop retrains on its own, but waiting for an
invisible threshold is not something anyone can present. The properties worth
holding are that it is authenticated, that it reports a playbook with no data
rather than failing, and that it defaults to all four.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import get_current_user_id, get_user_supabase
from app.main import app
from tests.simulator.conftest import MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    return fake


@pytest.fixture
def client(db: FakeSupabase) -> Any:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_training_with_no_data_reports_insufficient_rather_than_failing(
    client: TestClient,
) -> None:
    """Four playbooks with no history is the state right after onboarding."""
    response = client.post("/api/ml/uplift/train", json={})

    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert len(results) == 4
    assert {r["status"] for r in results} == {"insufficient_data"}
    assert all(r["minSamples"] == 10 for r in results)


def test_a_single_playbook_can_be_targeted(client: TestClient) -> None:
    response = client.post("/api/ml/uplift/train", json={"playbook": "b2b_overdue"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert [r["playbook"] for r in results] == ["b2b_overdue"]


def test_the_endpoint_requires_authentication() -> None:
    """No dependency override — the real auth dependency must reject."""
    with TestClient(app) as anonymous:
        assert anonymous.post("/api/ml/uplift/train", json={}).status_code in (401, 403)
