"""Scoping the audit log to a time window.

The batch results screen links here with the run's start time, so the filter is
load-bearing for a compliance claim: a reviewer following that link is being
told they are looking at one run. Returning the whole log under that heading
would be worse than returning nothing.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import get_current_user_id, get_user_supabase
from app.main import app
from tests.simulator.conftest import MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase

NOW = datetime.now(UTC)


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    for index, hours_ago in enumerate((48, 24, 2, 1)):
        fake.rows("audit_events").append(
            {
                "id": f"ev-{index}",
                "merchant_id": MERCHANT_ID,
                "actor": "agent",
                "event": "decide:arm_chosen",
                "created_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
            }
        )
    return fake


@pytest.fixture
def client(db: FakeSupabase) -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def events(client: TestClient, **params: Any) -> list[dict[str, Any]]:
    response = client.get("/api/audit", params=params)
    assert response.status_code == 200, response.text
    return response.json()["audit_events"]


def test_without_a_window_the_whole_log_comes_back(client: TestClient) -> None:
    assert len(events(client)) == 4


def test_a_window_excludes_everything_before_it(client: TestClient) -> None:
    since = (NOW - timedelta(hours=3)).isoformat()

    assert len(events(client, since=since)) == 2


def test_a_z_suffixed_timestamp_is_accepted(client: TestClient) -> None:
    """The shape JavaScript's `toISOString` produces, which is what the link carries."""
    since = (NOW - timedelta(hours=3)).isoformat().replace("+00:00", "Z")

    assert len(events(client, since=since)) == 2


def test_a_non_utc_offset_is_normalised_rather_than_compared_raw(
    client: TestClient,
) -> None:
    """Stored timestamps are UTC and the comparison is a string one.

    An IST-offset value compared as text sorts against the wrong instant — it
    would silently return events from five and a half hours off the window
    asked for.
    """
    ist = (NOW - timedelta(hours=3)).astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))

    assert len(events(client, since=ist.isoformat())) == 2


def test_an_unparseable_window_is_rejected_rather_than_ignored(client: TestClient) -> None:
    """Dropping the filter would return everything under a scoped heading."""
    response = client.get("/api/audit", params={"since": "last tuesday"})

    assert response.status_code == 422
    assert "ISO timestamp" in response.json()["error"]["message"]


def test_a_window_after_everything_returns_nothing_not_an_error(client: TestClient) -> None:
    """An empty window is a real answer: nothing happened then."""
    since = (NOW + timedelta(days=1)).isoformat()

    assert events(client, since=since) == []
