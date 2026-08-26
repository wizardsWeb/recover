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
def client(db: FakeSupabase) -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
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
