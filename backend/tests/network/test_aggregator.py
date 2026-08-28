"""Pooling retries into network cells.

An aggregator that is wrong does not fail — it writes a plausible rate, and the
detector alerts on it or stays quiet on it with equal confidence. So these tests
are about the ways a rate can be right-looking and wrong: the wrong timezone,
the wrong actions counted, a baseline that has voted on itself.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.ml.network.aggregator import (
    DEFAULT_BASELINE_RATE,
    IST,
    MIN_CELL_SAMPLES,
    aggregate_network_stats,
    get_historical_baseline,
    normalise_bank,
    normalise_method,
)
from tests.simulator.fake_supabase import FakeSupabase

MERCHANT = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"


def attempt(
    db: FakeSupabase,
    *,
    success: bool,
    bank: str = "SBI",
    method: str = "upi",
    minutes_ago: int = 1,
    action: str = "retry_charge",
    merchant: str = MERCHANT,
) -> None:
    db.rows("execution_attempts").append(
        {
            "id": f"att-{len(db.rows('execution_attempts'))}",
            "merchant_id": merchant,
            "action_type": action,
            "status": "success" if success else "failure",
            "request_payload": {"bank": bank, "method": method},
            "attempted_at": (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat(),
        }
    )


def seed_attempts(db: FakeSupabase, *, wins: int, losses: int, **kwargs: Any) -> None:
    for _ in range(wins):
        attempt(db, success=True, **kwargs)
    for _ in range(losses):
        attempt(db, success=False, **kwargs)


# ── Normalisation ──────────────────────────────────────────────────────


def test_bank_and_method_case_matches_what_the_guardrail_looks_up() -> None:
    """The silent failure this normalisation exists to prevent.

    The guardrail queries alerts with `bank.upper()` and `method.lower()`. A
    cell stored in any other case produces an alert that matches nothing, blocks
    nothing, and lets retries go on into a bank that is down — with no error
    anywhere.
    """
    assert normalise_bank(" sbi ") == "SBI"
    assert normalise_method(" UPI ") == "upi"
    assert normalise_bank(None) == "UNKNOWN"
    assert normalise_method("") == "unknown"


# ── What counts ────────────────────────────────────────────────────────


def test_only_retries_are_counted() -> None:
    """A WhatsApp send says nothing about whether a bank can settle a charge."""
    db = FakeSupabase()
    seed_attempts(db, wins=8, losses=2)
    for _ in range(50):
        attempt(db, success=False, action="send_whatsapp")

    aggregate_network_stats(db)

    row = db.rows("network_stats")[0]
    assert row["sample_size"] == 10
    assert row["success_rate"] == 0.8


def test_a_thin_cell_is_not_written() -> None:
    """One bad customer is not a signal about a bank."""
    db = FakeSupabase()
    seed_attempts(db, wins=0, losses=MIN_CELL_SAMPLES - 1)

    assert aggregate_network_stats(db) == 0
    assert db.rows("network_stats") == []


def test_a_cell_with_no_bank_is_dropped_rather_than_stored_as_unknown() -> None:
    """An UNKNOWN row can only dilute a baseline — nothing can act on it."""
    db = FakeSupabase()
    seed_attempts(db, wins=6, losses=4, bank="")

    assert aggregate_network_stats(db) == 0


def test_the_pool_spans_merchants_but_the_row_names_none_of_them() -> None:
    """The product argument and the privacy constraint, in one assertion.

    Pooling is the whole point — no single merchant sees enough failures to call
    an outage. What must never leave is which merchant contributed.
    """
    db = FakeSupabase()
    seed_attempts(db, wins=6, losses=0, merchant=MERCHANT)
    seed_attempts(db, wins=0, losses=6, merchant=OTHER)

    aggregate_network_stats(db)

    row = db.rows("network_stats")[0]
    assert row["sample_size"] == 12
    assert row["success_rate"] == 0.5
    assert "merchant_id" not in row
    assert MERCHANT not in str(row)


def test_rewards_are_pooled_as_trials_not_averaged_over_attempts() -> None:
    """A handful of rewards must not outvote a hundred attempts."""
    db = FakeSupabase()
    seed_attempts(db, wins=90, losses=10)
    for index in range(4):
        db.rows("bandit_rewards").append(
            {
                "id": f"rw-{index}",
                "merchant_id": MERCHANT,
                "context_vector": {"bank": "SBI", "method": "upi"},
                "reward_value": 0,
                "observed_at": datetime.now(UTC).isoformat(),
            }
        )

    aggregate_network_stats(db)

    row = db.rows("network_stats")[0]
    assert row["sample_size"] == 104
    # 90/104, not (0.9 + 0.0) / 2.
    assert row["success_rate"] == 0.865


# ── Time ───────────────────────────────────────────────────────────────


def test_the_hour_column_is_ist_not_utc() -> None:
    """A UTC hour would smear a bank's 9am across five and a half wrong hours."""
    db = FakeSupabase()
    seed_attempts(db, wins=6, losses=4)

    aggregate_network_stats(db)

    row = db.rows("network_stats")[0]
    assert row["hour_of_day"] == datetime.now(IST).hour
    assert row["day_of_week"] == datetime.now(IST).weekday()


def test_a_second_poll_in_the_same_hour_replaces_rather_than_appends() -> None:
    """Six overlapping rows an hour would have the baseline counting one retry six times."""
    db = FakeSupabase()
    seed_attempts(db, wins=6, losses=4)
    aggregate_network_stats(db)

    seed_attempts(db, wins=10, losses=0)
    aggregate_network_stats(db)

    assert len(db.rows("network_stats")) == 1
    assert db.rows("network_stats")[0]["sample_size"] == 20


def test_an_attempt_outside_the_window_is_not_counted() -> None:
    db = FakeSupabase()
    seed_attempts(db, wins=6, losses=4, minutes_ago=45)

    assert aggregate_network_stats(db) == 0


# ── The baseline ───────────────────────────────────────────────────────


def stat(
    db: FakeSupabase,
    *,
    rate: float,
    size: int,
    hours_ago: int,
    bank: str = "SBI",
    hour: int | None = None,
) -> None:
    end = datetime.now(UTC) - timedelta(hours=hours_ago)
    db.rows("network_stats").append(
        {
            "id": f"ns-{len(db.rows('network_stats'))}",
            "bank": bank,
            "method": "upi",
            "hour_of_day": datetime.now(IST).hour if hour is None else hour,
            "day_of_week": 0,
            "success_rate": rate,
            "sample_size": size,
            "window_start": end.isoformat(),
            "window_end": end.isoformat(),
        }
    )


def test_no_history_returns_the_conservative_default() -> None:
    """Not 1.0 — a default of 'everything always works' makes the first quiet hour an outage."""
    assert get_historical_baseline(FakeSupabase(), "SBI", "upi", 10) == DEFAULT_BASELINE_RATE


def test_the_baseline_is_weighted_by_sample_size() -> None:
    """A quiet 3am hour must not carry the weight of a 10am one."""
    db = FakeSupabase()
    hour = datetime.now(IST).hour
    stat(db, rate=0.9, size=400, hours_ago=25, hour=hour)
    stat(db, rate=0.5, size=10, hours_ago=49, hour=hour)

    baseline = get_historical_baseline(db, "SBI", "upi", hour)

    assert abs(baseline - (0.9 * 400 + 0.5 * 10) / 410) < 1e-9


def test_the_current_hour_does_not_vote_on_its_own_baseline() -> None:
    """The failure that makes a detector silently stop detecting.

    The aggregator writes this hour's reading moments before the detector asks
    what normal looks like. Counted, the baseline drifts to meet every anomaly
    and the z-score shrinks to nothing.
    """
    db = FakeSupabase()
    hour = datetime.now(IST).hour
    stat(db, rate=0.85, size=300, hours_ago=24, hour=hour)
    stat(db, rate=0.10, size=300, hours_ago=0, hour=hour)  # the degraded reading

    assert get_historical_baseline(db, "SBI", "upi", hour) == 0.85


def test_another_banks_history_is_not_borrowed() -> None:
    db = FakeSupabase()
    hour = datetime.now(IST).hour
    stat(db, rate=0.95, size=500, hours_ago=25, hour=hour, bank="HDFC")

    assert get_historical_baseline(db, "SBI", "upi", hour) == DEFAULT_BASELINE_RATE


def test_a_second_poll_replaces_even_in_the_first_minutes_of_an_hour() -> None:
    """The boundary the hourly key gets wrong if it is read from the wrong end.

    The window trails the measurement, so at 19:05 a reading covers 18:55-19:05
    and its `window_start` sits in the previous hour. Keyed on the start, the
    lookup misses the row it just wrote and inserts another — the overlapping
    rows this is supposed to prevent, for ten minutes out of every sixty, with
    the baseline counting the same retries twice.
    """
    from app.ml.network.aggregator import _Cell, _write_cell

    db = FakeSupabase()
    key = ("SBI", "upi", 19, 0)
    at_19_05 = datetime.now(UTC).replace(hour=19, minute=5, second=0, microsecond=0)

    for successes, trials in ((6.0, 10.0), (18.0, 20.0)):
        _write_cell(
            db,
            key,
            _Cell(successes=successes, trials=trials),
            at_19_05 - timedelta(minutes=10),
            at_19_05,
        )

    assert len(db.rows("network_stats")) == 1
    assert db.rows("network_stats")[0]["sample_size"] == 20
