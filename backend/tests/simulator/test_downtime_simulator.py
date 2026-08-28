"""The B3 downtime scenario.

The simulator's job is to produce the state a real detection produces, not a
convincing-looking approximation of it. Every assertion here is about that: the
same two rows, in the same case, in an order that never leaves the dashboard
claiming an outage the guardrail is not yet enforcing.
"""

import asyncio
import contextlib
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.guardrail import run_guardrail
from app.api import simulator as module
from app.ml.network.aggregator import IST
from tests.simulator.conftest import MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase

B3 = {"bank": "SBI", "method": "upi", "severity": "high", "durationMinutes": 30}


@pytest.fixture(autouse=True)
def service_db(
    client: TestClient, db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> FakeSupabase:
    """Point the service-role client at the same fake the caller's client uses.

    Depends on `client` so it patches *after* the shared fixture does — that one
    aims the service client at an empty database to keep the agent loop away
    from these tests, and the last writer wins.

    Convenient for every other assertion in this file, and deliberately *not*
    used by `test_the_network_tables_are_written_with_the_service_role`, which
    hands the two clients separate databases so the distinction is visible.
    """
    monkeypatch.setattr(module, "get_service_client", lambda: db)
    return db


@pytest.fixture(autouse=True)
def captured_publishes(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record what reached the alerts channel, without needing a Redis."""
    seen: list[dict[str, Any]] = []

    async def fake_publish(redis_client: Any, payload: dict[str, Any]) -> None:
        seen.append(payload)

    monkeypatch.setattr(module, "publish_alert", fake_publish)
    monkeypatch.setattr(module, "get_redis_client", lambda: None)
    return seen


# ── What it writes ─────────────────────────────────────────────────────


def test_an_outage_writes_both_the_alert_and_the_reading_behind_it(
    client: TestClient, db: FakeSupabase
) -> None:
    """One without the other is a half-state nobody can explain.

    An alert with no stats shows a banner over an unremarkable heatmap; a stats
    row with no alert degrades the grid and blocks nothing.
    """
    response = client.post("/api/simulator/network/downtime", json=B3)

    assert response.status_code == 200, response.text
    alert = db.rows("network_alerts")[0]
    stat = db.rows("network_stats")[0]

    assert alert["alert_type"] == "downtime"
    assert alert["severity"] == "high"
    assert alert["network_wide_success_rate"] == 0.41
    assert alert["resolved_at"] is None
    assert stat["success_rate"] == 0.41
    assert stat["hour_of_day"] == __import__("datetime").datetime.now(IST).hour


def test_the_network_tables_are_written_with_the_service_role(
    client: TestClient, db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`network_alerts` and `network_stats` are global reference tables.

    Their RLS grants an authenticated user `SELECT` and nothing else, so writing
    them through the caller's client fails with 42501 — a 500 the endpoint has
    no way to explain. `FakeSupabase` does not enforce RLS and never will, so
    the property is asserted structurally instead: hand the two clients separate
    databases, and check the rows land in the privileged one.
    """
    service = FakeSupabase()
    monkeypatch.setattr(module, "get_service_client", lambda: service)

    assert client.post("/api/simulator/network/downtime", json=B3).status_code == 200

    assert len(service.rows("network_alerts")) == 1
    assert len(service.rows("network_stats")) == 1
    assert db.rows("network_alerts") == []
    assert db.rows("network_stats") == []


def test_the_bank_and_method_are_stored_in_the_case_the_guardrail_queries(
    client: TestClient, db: FakeSupabase
) -> None:
    """The whole scenario turns on this and it fails silently when wrong."""
    client.post(
        "/api/simulator/network/downtime",
        json={**B3, "bank": "sbi", "method": "UPI"},
    )

    alert = db.rows("network_alerts")[0]
    assert alert["affected_bank"] == "SBI"
    assert alert["affected_method"] == "upi"


@pytest.mark.parametrize(
    ("severity", "rate"), [("critical", 0.20), ("high", 0.41), ("medium", 0.58)]
)
def test_each_severity_degrades_by_its_own_amount(
    client: TestClient, db: FakeSupabase, severity: str, rate: float
) -> None:
    client.post("/api/simulator/network/downtime", json={**B3, "severity": severity})

    assert db.rows("network_stats")[0]["success_rate"] == rate


def test_a_second_outage_on_the_same_instrument_is_refused(client: TestClient) -> None:
    """Two open alerts for one bank would leave one un-lifted after the first resolves."""
    client.post("/api/simulator/network/downtime", json=B3)

    assert client.post("/api/simulator/network/downtime", json=B3).status_code == 409


def test_the_simulated_outage_is_one_the_real_detector_would_also_have_called(
    client: TestClient, db: FakeSupabase
) -> None:
    """Otherwise the demo proves only that the simulator believes itself."""
    from app.ml.network.detector import MIN_ALERT_SAMPLES, severity_for, z_score

    client.post("/api/simulator/network/downtime", json=B3)
    stat = db.rows("network_stats")[0]

    assert stat["sample_size"] >= MIN_ALERT_SAMPLES
    assert severity_for(z_score(stat["success_rate"], 0.82, stat["sample_size"])) is not None


@pytest.mark.parametrize("duration", [0, 1000])
def test_an_out_of_range_duration_is_rejected(client: TestClient, duration: int) -> None:
    """A zero-minute outage resolves before anyone sees it; an eight-hour one
    outlives the process that would have lifted it."""
    response = client.post(
        "/api/simulator/network/downtime", json={**B3, "durationMinutes": duration}
    )
    assert response.status_code == 422


# ── Ordering ───────────────────────────────────────────────────────────


def test_the_blocking_row_lands_before_the_banner_is_told(
    client: TestClient, db: FakeSupabase, captured_publishes: list[dict[str, Any]]
) -> None:
    """Publishing first opens a window where the dashboard says a bank is down
    while the agent is still retrying into it."""
    assert db.rows("network_alerts") == []

    client.post("/api/simulator/network/downtime", json=B3)

    assert len(captured_publishes) == 1
    assert captured_publishes[0]["type"] == "alert_fired"
    assert captured_publishes[0]["alert"]["id"] == db.rows("network_alerts")[0]["id"]


def test_the_alert_payload_carries_no_merchant_identifiers(
    client: TestClient, captured_publishes: list[dict[str, Any]]
) -> None:
    client.post("/api/simulator/network/downtime", json=B3)

    assert MERCHANT_ID not in json.dumps(captured_publishes[0], default=str)


# ── The point of it all ────────────────────────────────────────────────


async def test_the_guardrail_blocks_a_retry_into_the_downed_bank(
    client: TestClient, db: FakeSupabase
) -> None:
    """B3, end to end: the alert exists, so the retry does not go out.

    This is the assertion the whole network subsystem is for. Everything else —
    the aggregator, the detector, the poller — exists to put this row in this
    table so that this call returns BLOCK.
    """
    case = {
        "id": "case-b3",
        "merchant_id": MERCHANT_ID,
        "playbook": "subscription_failure",
        "metadata": {"bank": "SBI", "method": "upi"},
    }
    decision = {"action_type": "retry_charge", "chosen_arm": "retry_now"}
    customer = {"id": "cust-b3", "consent": {"whatsapp": True}}

    before = await run_guardrail(case, decision, customer, db)
    assert before.verdict != "BLOCK"

    client.post("/api/simulator/network/downtime", json=B3)

    after = await run_guardrail(case, decision, customer, db)
    assert after.verdict == "BLOCK"
    assert after.blocking_check == "network_bank_health"


# ── Auto-resolution ────────────────────────────────────────────────────


async def test_the_outage_lifts_itself_and_announces_it(
    db: FakeSupabase, captured_publishes: list[dict[str, Any]]
) -> None:
    """Called with no delay so the timer's body is exercised, not its patience."""
    db.rows("network_alerts").append(
        {"id": "alert-1", "affected_bank": "SBI", "affected_method": "upi", "resolved_at": None}
    )

    await module._lift_downtime(db, "alert-1", "SBI", "upi", 0)

    assert db.rows("network_alerts")[0]["resolved_at"] is not None
    assert captured_publishes[-1]["type"] == "alert_resolved"
    # The bank is left healthy, so the real resolver would agree on the next
    # poll rather than racing this one.
    assert db.rows("network_stats")[0]["success_rate"] > 0.8


async def test_a_lift_that_fails_does_not_surface_as_a_task_exception(
    db: FakeSupabase,
) -> None:
    """It runs detached from any request, so a raise here is only a log line —
    and the visible symptom would be an outage that never lifts."""

    class Broken:
        def table(self, name: str) -> Any:
            raise ConnectionError("supabase unavailable")

    await module._lift_downtime(Broken(), "alert-1", "SBI", "upi", 0)


def test_the_pending_timer_is_strongly_referenced(client: TestClient) -> None:
    """The loop keeps only a weak reference to a task nobody holds.

    Collected mid-sleep it does not raise — the outage simply never lifts, and
    the guardrail goes on blocking retries into a bank that came back.

    The task belongs to the test client's own event loop, so it is cancelled
    through the portal rather than awaited from here — awaiting a foreign loop's
    future is a different error, and one that would mask this assertion.
    """
    client.post("/api/simulator/network/downtime", json=B3)

    assert len(module._PENDING_RESOLUTIONS) == 1
    task = next(iter(module._PENDING_RESOLUTIONS))

    async def cancel_and_wait() -> None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    client.portal.call(cancel_and_wait)

    # And the set does not grow without bound.
    assert set() == module._PENDING_RESOLUTIONS


# ── Gating ─────────────────────────────────────────────────────────────


def test_the_endpoint_requires_authentication() -> None:
    from app.main import app

    # The autouse fixtures above pull in the shared `client`, which installs
    # dependency overrides on the application object. They have to come back off
    # for the real auth dependency to be what answers.
    app.dependency_overrides.clear()
    with TestClient(app) as anonymous:
        assert anonymous.post("/api/simulator/network/downtime", json=B3).status_code in (401, 403)
