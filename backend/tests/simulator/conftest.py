"""Fixtures for the simulator tests.

The FastAPI dependencies are overridden rather than mocked at the module level:
``get_current_user_id`` and ``get_user_supabase`` are the seam the whole router
is written against, so replacing them exercises every line of routing, request
validation and response serialisation with a fake database underneath.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import get_current_user_id, get_user_supabase
from app.main import app
from tests.simulator.fake_supabase import FakeSupabase

#: A stable UUID standing in for the signed-in merchant (merchants.id = auth.uid()).
MERCHANT_ID = "11111111-1111-4111-8111-111111111111"

#: A second merchant, for asserting that one merchant's data stays out of the other's.
OTHER_MERCHANT_ID = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    fake.seed_merchant(OTHER_MERCHANT_ID)
    return fake


@pytest.fixture
def client(db: FakeSupabase, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db

    # Firing a scenario queues the agent loop on the service-role client, which
    # `get_service_client` would otherwise build against the real Supabase URL.
    # These tests are about what the *simulator* writes, so the background task
    # is pointed at an empty database: it finds no event and returns without
    # touching `db`. The agent's own behaviour is covered in tests/agent and
    # tests/scenarios, where the clock is pinned — running it here would make
    # every simulator assertion depend on what time of day the suite ran.
    empty = FakeSupabase()
    monkeypatch.setattr("app.api.simulator.get_service_client", lambda: empty)
    monkeypatch.setattr("app.api.events.get_service_client", lambda: empty)
    # Fixture loading publishes the causal graph, which is global reference data
    # and so needs the service role. Left unpatched, every load builds a real
    # Supabase client against the stub URL in `tests/conftest.py` and waits for
    # it to fail — swallowed, so it shows up as a slow suite rather than an
    # error.
    monkeypatch.setattr("app.simulator.loader.get_service_client", lambda: db)

    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def loaded_client(client: TestClient) -> TestClient:
    """A client whose merchant already has the fixture set loaded."""
    response = client.post("/api/simulator/fixtures/load")
    assert response.status_code == 200, response.text
    return client


def rows(db: FakeSupabase, table: str, **filters: Any) -> list[dict[str, Any]]:
    """Every row in ``table`` matching the given column equalities."""
    return [
        row
        for row in db.rows(table)
        if all(row.get(column) == value for column, value in filters.items())
    ]
