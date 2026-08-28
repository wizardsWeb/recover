"""The network intelligence endpoints.

The router reads pooled data, so the usual "RLS scopes it" argument does not
apply and the properties have to be asserted directly: what leaves the process,
what an empty network says instead of guessing, and — for the benchmark — that a
peer group small enough to identify is refused rather than served.
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from app.api import network as module
from app.api.network import HEATMAP_BANKS, MIN_PEER_CASES, MIN_PEER_MERCHANTS
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
def client(db: FakeSupabase) -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def stat(
    db: FakeSupabase,
    *,
    bank: str,
    hour: int,
    rate: float,
    size: int = 200,
    method: str = "upi",
    hours_ago: float = 0,
) -> None:
    end = datetime.now(UTC) - timedelta(hours=hours_ago)
    db.rows("network_stats").append(
        {
            "id": f"ns-{len(db.rows('network_stats'))}",
            "bank": bank,
            "method": method,
            "hour_of_day": hour,
            "day_of_week": 0,
            "success_rate": rate,
            "sample_size": size,
            "window_start": end.isoformat(),
            "window_end": end.isoformat(),
        }
    )


def alert(
    db: FakeSupabase, *, bank: str = "SBI", resolved: bool = False, hours_ago: int = 0
) -> None:
    detected = datetime.now(UTC) - timedelta(hours=hours_ago)
    db.rows("network_alerts").append(
        {
            "id": f"al-{len(db.rows('network_alerts'))}",
            "alert_type": "degradation",
            "affected_bank": bank,
            "affected_method": "upi",
            "severity": "high",
            "z_score": -4.2,
            "sample_size": 300,
            "affected_merchants_count": 8,
            "network_wide_success_rate": 0.2,
            "baseline_rate": 0.85,
            "detected_at": detected.isoformat(),
            "resolved_at": detected.isoformat() if resolved else None,
        }
    )


def case(
    db: FakeSupabase, *, merchant: str, recovered: bool, playbook: str = "subscription_failure"
) -> None:
    db.rows("recovery_cases").append(
        {
            "id": f"c-{len(db.rows('recovery_cases'))}",
            "merchant_id": merchant,
            "playbook": playbook,
            "status": "recovered" if recovered else "stopped",
            "closed_at": "2026-08-01T00:00:00Z",
            "amount_recovered_cents": 100_000 if recovered else 0,
        }
    )


# ── Heatmap ────────────────────────────────────────────────────────────


def test_the_grid_draws_every_bank_even_the_quiet_ones(
    client: TestClient, db: FakeSupabase
) -> None:
    """A bank that saw no traffic is a blank row, not a smaller network."""
    stat(db, bank="SBI", hour=10, rate=0.8)

    body = client.get("/api/network/heatmap").json()

    assert body["banks"] == list(HEATMAP_BANKS)
    assert body["hours"] == list(range(24))


def test_a_cell_shows_its_latest_reading_not_a_weekly_average(
    client: TestClient, db: FakeSupabase
) -> None:
    """An average with six healthy days in it renders a live outage green."""
    for day in range(1, 7):
        stat(db, bank="SBI", hour=10, rate=0.85, hours_ago=24 * day)
    stat(db, bank="SBI", hour=10, rate=0.20, hours_ago=0)

    cells = client.get("/api/network/heatmap").json()["cells"]
    sbi = next(cell for cell in cells if cell["bank"] == "SBI" and cell["hour"] == 10)

    assert sbi["success_rate"] == 0.2


def test_the_method_filter_narrows_the_grid(client: TestClient, db: FakeSupabase) -> None:
    stat(db, bank="HDFC", hour=9, rate=0.82, method="card")
    stat(db, bank="HDFC", hour=9, rate=0.61, method="upi")

    cells = client.get("/api/network/heatmap", params={"method": "CARD"}).json()["cells"]

    assert [cell["success_rate"] for cell in cells] == [0.82]


def test_an_empty_network_says_so_rather_than_rendering_grey_squares(
    client: TestClient,
) -> None:
    body = client.get("/api/network/heatmap").json()

    assert body["cells"] == []
    assert "seeder" in body["note"]


def test_a_mostly_thin_grid_is_flagged_as_sparse(client: TestClient, db: FakeSupabase) -> None:
    for hour in range(6):
        stat(db, bank="SBI", hour=hour, rate=0.8, size=2)
    stat(db, bank="HDFC", hour=9, rate=0.8, size=400)

    assert client.get("/api/network/heatmap").json()["is_sparse"] is True


def test_the_grid_carries_no_merchant_identifiers(client: TestClient, db: FakeSupabase) -> None:
    """The heatmap is pooled by construction — nothing to scope, nothing to leak."""
    stat(db, bank="SBI", hour=10, rate=0.8)

    body = client.get("/api/network/heatmap").text

    assert MERCHANT_ID not in body
    assert OTHER_MERCHANT_ID not in body


# ── Alerts ─────────────────────────────────────────────────────────────


def test_open_and_recently_resolved_alerts_are_reported_separately(
    client: TestClient, db: FakeSupabase
) -> None:
    alert(db, bank="SBI")
    alert(db, bank="HDFC", resolved=True, hours_ago=2)

    body = client.get("/api/network/alerts").json()

    assert body["total_active"] == 1
    assert [a["bank"] for a in body["active"]] == ["SBI"]
    assert [a["bank"] for a in body["recent"]] == ["HDFC"]


def test_a_long_running_outage_is_still_reported_as_active(
    client: TestClient, db: FakeSupabase
) -> None:
    """The most important thing on the page must not fall out of a 24h window."""
    alert(db, bank="SBI", hours_ago=72)

    body = client.get("/api/network/alerts").json()

    assert body["total_active"] == 1


def test_a_healthy_network_reports_a_checked_at_timestamp(client: TestClient) -> None:
    """'All banks healthy' is only trustworthy if it says when it last looked."""
    body = client.get("/api/network/alerts").json()

    assert body["active"] == []
    assert body["checked_at"]


# ── Benchmark ──────────────────────────────────────────────────────────


def seed_peers(db: FakeSupabase, count: int, *, wins: int = 3) -> None:
    for index in range(count):
        merchant = f"peer-{index}"
        for slot in range(MIN_PEER_CASES):
            case(db, merchant=merchant, recovered=slot < wins)


def test_a_network_too_small_to_anonymise_refuses_to_report_a_median(
    client: TestClient, db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With one other merchant, 'the vertical median' is that merchant's rate.

    Calling it a summary statistic does not make it less of a disclosure, so the
    endpoint says the network is too small instead.
    """
    monkeypatch.setattr(module, "get_service_client", lambda: db)
    for _ in range(4):
        case(db, merchant=MERCHANT_ID, recovered=True)
    seed_peers(db, MIN_PEER_MERCHANTS - 1)

    body = client.get("/api/network/benchmark").json()

    assert body["merchant_rate"] == 1.0
    assert body["vertical_median"] is None
    assert body["basis"] == "network_too_small"


def test_a_large_enough_network_reports_the_distribution(
    client: TestClient, db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "get_service_client", lambda: db)
    for slot in range(10):
        case(db, merchant=MERCHANT_ID, recovered=slot < 9)
    seed_peers(db, MIN_PEER_MERCHANTS + 3, wins=2)

    body = client.get("/api/network/benchmark").json()

    assert body["merchant_rate"] == 0.9
    assert body["vertical_median"] == 0.4
    assert body["percentile"] == 100
    assert body["basis"] == "network"


def test_the_benchmark_returns_statistics_never_a_peers_rows(
    client: TestClient, db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The privacy property, asserted on the wire rather than argued for."""
    monkeypatch.setattr(module, "get_service_client", lambda: db)
    for _ in range(6):
        case(db, merchant=MERCHANT_ID, recovered=True)
    seed_peers(db, MIN_PEER_MERCHANTS + 2)

    body = client.get("/api/network/benchmark").text

    assert "peer-0" not in body
    assert OTHER_MERCHANT_ID not in body


def test_a_merchant_with_no_closed_cases_gets_nulls_not_zero(client: TestClient) -> None:
    """A 0% recovery rate and an unmeasured one are different claims."""
    body = client.get("/api/network/benchmark").json()

    assert body["merchant_rate"] is None
    assert body["basis"] == "no_closed_cases"


def test_a_peer_read_failure_still_returns_the_merchants_own_rate(
    client: TestClient, db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A benchmark is a nice-to-have; the caller's own number is not."""

    def explode() -> Any:
        raise ConnectionError("service client unavailable")

    monkeypatch.setattr(module, "get_service_client", explode)
    for _ in range(4):
        case(db, merchant=MERCHANT_ID, recovered=True)

    body = client.get("/api/network/benchmark").json()

    assert body["merchant_rate"] == 1.0
    assert body["basis"] == "network_too_small"


def test_the_merchants_own_rate_excludes_other_merchants_cases(
    client: TestClient, db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "get_service_client", lambda: db)
    case(db, merchant=MERCHANT_ID, recovered=True)
    for _ in range(20):
        case(db, merchant=OTHER_MERCHANT_ID, recovered=False)

    assert client.get("/api/network/benchmark").json()["merchant_rate"] == 1.0


# ── Auth ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path", ["/api/network/heatmap", "/api/network/alerts", "/api/network/benchmark"]
)
def test_every_endpoint_requires_authentication(path: str) -> None:
    with TestClient(app) as anonymous:
        assert anonymous.get(path).status_code in (401, 403)


# ── The live stream ────────────────────────────────────────────────────


@pytest.mark.parametrize("query", ["", "?token=not-a-jwt"])
def test_the_stream_refuses_an_unverified_connection(query: str) -> None:
    """Verified before the socket is accepted, not after.

    A close during the handshake surfaces client-side as a failure to connect,
    which is the behaviour wanted: an unauthenticated caller never reaches a
    state where it is waiting for messages that will not come.
    """
    with (
        TestClient(app) as anonymous,
        pytest.raises(WebSocketDisconnect),
        anonymous.websocket_connect(f"/api/network/alerts/stream{query}") as socket,
    ):
        socket.receive_json()


def test_a_verified_socket_receives_published_alerts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end-to-end path: publish on the channel, arrive at the browser."""
    monkeypatch.setattr(module, "verify_supabase_jwt", lambda token: {"sub": MERCHANT_ID})

    import fakeredis.aioredis

    shared = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(module, "get_redis_client", lambda: shared)

    with client.websocket_connect("/api/network/alerts/stream?token=stub") as socket:
        assert socket.receive_json()["type"] == "connected"

        payload = {"type": "alert_fired", "alert": {"affected_bank": "SBI"}}
        # The socket's own event loop is the one that must publish, so the send
        # is driven through the portal the test client already owns.
        client.portal.call(shared.publish, "network:alerts", json.dumps(payload))

        assert socket.receive_json() == payload


def test_the_subscription_is_torn_down_when_the_socket_closes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pub/sub connection that outlives its socket is not merely a leak.

    Redis goes on delivering to it, so a server open for a week accumulates one
    dead subscriber per dropped browser tab and fans out to none of them.
    """
    monkeypatch.setattr(module, "verify_supabase_jwt", lambda token: {"sub": MERCHANT_ID})

    import fakeredis.aioredis

    shared = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(module, "get_redis_client", lambda: shared)

    with client.websocket_connect("/api/network/alerts/stream?token=stub") as socket:
        socket.receive_json()

    subscribers = client.portal.call(shared.pubsub_numsub, "network:alerts")
    assert subscribers[0][1] == 0
