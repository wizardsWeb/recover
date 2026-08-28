"""The seeded network history.

The heatmap's claim is that *when* matters. A grid seeded from uniform noise
would render as static and reduce that claim to decoration, so the tests here
are about whether the generated week actually contains the shapes the page
asserts — and whether the detector, reading the same rows, agrees.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import simulator as module
from app.ml.network.aggregator import IST, get_historical_baseline
from app.simulator.network_seed import INSTRUMENTS, MAX_DAYS, seed_network_stats
from tests.simulator.fake_supabase import FakeSupabase


@pytest.fixture
def seeded() -> FakeSupabase:
    db = FakeSupabase()
    seed_network_stats(db, days=7, seed=4)
    return db


def cells(db: FakeSupabase, bank: str, method: str) -> list[dict[str, Any]]:
    return [
        row for row in db.rows("network_stats") if row["bank"] == bank and row["method"] == method
    ]


def rate_at(db: FakeSupabase, bank: str, method: str, hour: int) -> float:
    matching = [row for row in cells(db, bank, method) if row["hour_of_day"] == hour]
    return sum(row["success_rate"] for row in matching) / len(matching)


# ── Shape ──────────────────────────────────────────────────────────────


def test_a_week_of_hourly_readings_lands_for_every_instrument(seeded: FakeSupabase) -> None:
    rows = seeded.rows("network_stats")

    assert len(rows) > 1000
    assert {row["bank"] for row in rows} == {"HDFC", "ICICI", "SBI", "AXIS", "PAYTM"}
    assert {row["method"] for row in rows} >= {"upi", "card", "netbanking", "wallet"}


def test_no_reading_is_dated_in_the_future(seeded: FakeSupabase) -> None:
    """A future 'current' cell hands the detector a reading that has not occurred."""
    now = datetime.now(UTC).isoformat()

    assert all(row["window_end"] <= now for row in seeded.rows("network_stats"))


def test_the_hour_column_is_ist(seeded: FakeSupabase) -> None:
    """It has to match what the aggregator writes, or the two disagree per cell."""
    for row in seeded.rows("network_stats")[:50]:
        moment = datetime.fromisoformat(row["window_end"]).astimezone(IST)
        assert row["hour_of_day"] == moment.hour
        assert row["day_of_week"] == moment.weekday()


def test_a_fixed_seed_reproduces_the_grid() -> None:
    """A demo whose heatmap differs on every run is one nobody can rehearse."""
    grids = []
    for _ in range(2):
        db = FakeSupabase()
        seed_network_stats(db, days=3, seed=11)
        grids.append(
            [(r["bank"], r["hour_of_day"], r["success_rate"]) for r in db.rows("network_stats")]
        )

    assert grids[0] == grids[1]


def test_reseeding_replaces_rather_than_stacking() -> None:
    """Two readings per cell would average a seeded week against itself."""
    db = FakeSupabase()
    first = seed_network_stats(db, days=3, seed=1)
    second = seed_network_stats(db, days=3, seed=2)

    assert second["cleared"] == first["rows"]
    assert len(db.rows("network_stats")) == second["rows"]


# ── The findings the page claims ───────────────────────────────────────


def test_hdfc_cards_really_do_collapse_late_at_night(seeded: FakeSupabase) -> None:
    """The headline insight on the benchmark panel, asserted against the data.

    A static claim beside a grid that does not show it is the one dishonest
    thing this page could contain.
    """
    morning = rate_at(seeded, "HDFC", "card", 9)
    late = rate_at(seeded, "HDFC", "card", 23)

    assert morning - late > 0.3


def test_an_unremarkable_bank_stays_unremarkable(seeded: FakeSupabase) -> None:
    """A grid where all five banks had a finding is a grid nobody believes."""
    spread = max(rate_at(seeded, "AXIS", "card", hour) for hour in range(24)) - min(
        rate_at(seeded, "AXIS", "card", hour) for hour in range(24)
    )

    assert spread < 0.15


def test_volume_follows_the_hour_not_the_rate(seeded: FakeSupabase) -> None:
    """Uniform sample sizes would never exercise the thin-cell floor or watermark."""
    peak = [r["sample_size"] for r in cells(seeded, "HDFC", "card") if r["hour_of_day"] == 11]
    trough = [r["sample_size"] for r in cells(seeded, "HDFC", "card") if r["hour_of_day"] == 4]

    assert min(peak) > max(trough) * 3


def test_the_seeded_incidents_are_visible_as_degradations(seeded: FakeSupabase) -> None:
    """They are what give a live outage a baseline to have recovered to."""
    incident = [
        row["success_rate"] for row in cells(seeded, "SBI", "upi") if row["success_rate"] < 0.5
    ]

    assert len(incident) >= 5


def test_the_baseline_computed_from_the_seed_is_plausible(seeded: FakeSupabase) -> None:
    """The seeder and the detector have to agree, or the demo proves nothing."""
    baseline = get_historical_baseline(seeded, "ICICI", "upi", 10)

    assert 0.7 < baseline < 0.95


# ── The endpoint ───────────────────────────────────────────────────────


def test_the_endpoint_populates_the_heatmap(
    client: TestClient, db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "get_service_client", lambda: db)

    response = client.post("/api/simulator/network/seed", json={"days": 7, "seed": 3})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rows"] > 1000
    assert body["banks"] == ["AXIS", "HDFC", "ICICI", "PAYTM", "SBI"]
    assert len(db.rows("network_stats")) == body["rows"]


@pytest.mark.parametrize("days", [0, MAX_DAYS + 1])
def test_an_out_of_range_window_is_rejected(client: TestClient, days: int) -> None:
    assert client.post("/api/simulator/network/seed", json={"days": days}).status_code == 422


def test_the_endpoint_requires_authentication() -> None:
    from app.main import app

    with TestClient(app) as anonymous:
        assert anonymous.post("/api/simulator/network/seed", json={}).status_code in (401, 403)


def test_every_instrument_declares_a_full_day_of_multipliers() -> None:
    """A short tuple would index-error on the hour it was missing, at 3am."""
    assert all(len(instrument.hourly) == 24 for instrument in INSTRUMENTS)
