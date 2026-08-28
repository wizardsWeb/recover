"""Deciding a bank is down.

An alert here blocks retries for every merchant on the network, so a false
positive costs real recovery attempts and a stuck alert costs them for longer.
Both directions are tested: what must fire, and what must not.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from app.ml.network.aggregator import DEFAULT_BASELINE_RATE, IST
from app.ml.network.detector import (
    ALERTS_CHANNEL,
    MIN_ALERT_AGE_MINUTES,
    MIN_ALERT_SAMPLES,
    detect_anomalies,
    find_anomalies,
    find_resolved_alerts,
    resolve_stale_alerts,
    severity_for,
    z_score,
)
from tests.simulator.fake_supabase import FakeSupabase

MERCHANT = "11111111-1111-4111-8111-111111111111"


class FakeRedis:
    """Records what was published, so the broadcast can be asserted on."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, json.loads(payload)))


def cell(
    db: FakeSupabase,
    *,
    rate: float,
    size: int,
    hours_ago: float = 0,
    bank: str = "SBI",
    method: str = "upi",
    hour: int | None = None,
) -> None:
    end = datetime.now(UTC) - timedelta(hours=hours_ago)
    db.rows("network_stats").append(
        {
            "id": f"ns-{len(db.rows('network_stats'))}",
            "bank": bank,
            "method": method,
            "hour_of_day": datetime.now(IST).hour if hour is None else hour,
            "day_of_week": 0,
            "success_rate": rate,
            "sample_size": size,
            "window_start": end.isoformat(),
            "window_end": end.isoformat(),
        }
    )


def history(db: FakeSupabase, *, rate: float, bank: str = "SBI", method: str = "upi") -> None:
    """A week of healthy readings for the current hour, on previous days."""
    for day in range(1, 8):
        cell(db, rate=rate, size=300, hours_ago=24 * day, bank=bank, method=method)


def degraded(db: FakeSupabase, *, rate: float, size: int = 200) -> None:
    history(db, rate=0.85)
    cell(db, rate=rate, size=size)


# ── The statistic ──────────────────────────────────────────────────────


def test_a_bigger_sample_makes_the_same_drop_more_surprising() -> None:
    """The property that makes one threshold work across cells of every size."""
    small = z_score(0.60, 0.85, 20)
    large = z_score(0.60, 0.85, 500)

    assert large < small < 0


def test_the_error_bar_comes_from_the_baseline_not_the_observation() -> None:
    """Otherwise a catastrophic reading shrinks its own error and looks calmer.

    At an observed rate of 0, the observed-proportion standard error is exactly
    zero. Using it would make a total outage report a z-score of zero — the one
    reading that must never look normal.
    """
    assert z_score(0.0, 0.85, 100) < -20


def test_a_degenerate_baseline_does_not_divide_by_zero() -> None:
    assert z_score(0.5, 1.0, 100) < 0
    assert z_score(0.5, 0.0, 100) > 0
    assert z_score(0.5, 0.85, 0) == 0.0


def test_severity_bands_are_where_the_product_says_they_are() -> None:
    assert severity_for(-4.0) == "critical"
    assert severity_for(-3.5) == "high"
    assert severity_for(-3.2) == "high"
    assert severity_for(-3.0) == "medium"
    assert severity_for(-2.6) == "medium"
    assert severity_for(-2.5) is None
    assert severity_for(0.0) is None
    assert severity_for(5.0) is None


# ── What fires ─────────────────────────────────────────────────────────


def test_a_real_degradation_fires_with_the_numbers_behind_it() -> None:
    db = FakeSupabase()
    degraded(db, rate=0.20)

    fired = find_anomalies(db)

    assert len(fired) == 1
    alert = db.rows("network_alerts")[0]
    assert alert["affected_bank"] == "SBI"
    assert alert["affected_method"] == "upi"
    assert alert["severity"] == "critical"
    assert alert["baseline_rate"] == 0.85
    assert alert["network_wide_success_rate"] == 0.2
    assert alert["z_score"] < -3.5
    assert alert["resolved_at"] is None


def test_the_bank_and_method_are_stored_in_the_case_the_guardrail_queries() -> None:
    """The guardrail looks up `bank.upper()` and `method.lower()`.

    An alert in any other case matches nothing and blocks nothing, and there is
    no error anywhere to say so — the retries simply keep going into a bank
    that is down.
    """
    db = FakeSupabase()
    history(db, rate=0.85, bank="sbi", method="UPI")
    cell(db, rate=0.20, size=200, bank="sbi", method="UPI")

    find_anomalies(db)

    alert = db.rows("network_alerts")[0]
    assert alert["affected_bank"] == "SBI"
    assert alert["affected_method"] == "upi"


def test_a_statistically_certain_but_trivial_dip_does_not_fire() -> None:
    """The condition that keeps an alert worth interrupting someone for.

    With 5,000 samples a drop from 85% to 81% clears any z-threshold you like.
    It is also four points, which is not something to block a network's retries
    over.
    """
    db = FakeSupabase()
    history(db, rate=0.85)
    cell(db, rate=0.81, size=5000)

    assert find_anomalies(db) == []


def test_a_large_drop_on_a_thin_sample_does_not_fire() -> None:
    """Eight retries going badly is a bad afternoon, not an outage."""
    db = FakeSupabase()
    history(db, rate=0.85)
    cell(db, rate=0.10, size=MIN_ALERT_SAMPLES - 1)

    assert find_anomalies(db) == []


def test_an_improvement_never_fires() -> None:
    db = FakeSupabase()
    history(db, rate=0.40)
    cell(db, rate=0.95, size=400)

    assert find_anomalies(db) == []


def test_a_second_poll_does_not_duplicate_an_open_alert() -> None:
    """Re-firing would also reset the resolution clock, so nothing would ever clear."""
    db = FakeSupabase()
    degraded(db, rate=0.20)

    find_anomalies(db)
    assert find_anomalies(db) == []
    assert len(db.rows("network_alerts")) == 1


def test_a_cell_with_no_history_is_judged_against_the_conservative_default() -> None:
    """Week one still has to be able to detect an outage."""
    db = FakeSupabase()
    cell(db, rate=0.05, size=400)

    fired = find_anomalies(db)

    assert len(fired) == 1
    assert db.rows("network_alerts")[0]["baseline_rate"] == round(DEFAULT_BASELINE_RATE, 3)


def test_the_alert_counts_affected_merchants_without_naming_them() -> None:
    """'And it is hitting eight of you' is the sentence that sells a network product."""
    db = FakeSupabase()
    degraded(db, rate=0.20)
    for index in range(8):
        db.rows("execution_attempts").append(
            {
                "id": f"att-{index}",
                "merchant_id": f"merchant-{index}",
                "action_type": "retry_charge",
                "status": "failure",
                "request_payload": {"bank": "SBI", "method": "upi"},
                "attempted_at": datetime.now(UTC).isoformat(),
            }
        )

    find_anomalies(db)

    alert = db.rows("network_alerts")[0]
    assert alert["affected_merchants_count"] == 8
    assert "merchant-3" not in json.dumps(alert, default=str)


# ── Resolution ─────────────────────────────────────────────────────────


def open_alert(db: FakeSupabase, *, minutes_ago: int, baseline: float = 0.85) -> None:
    db.rows("network_alerts").append(
        {
            "id": "alert-1",
            "alert_type": "degradation",
            "affected_bank": "SBI",
            "affected_method": "upi",
            "severity": "high",
            "baseline_rate": baseline,
            "detected_at": (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat(),
            "resolved_at": None,
        }
    )


def test_a_recovered_instrument_clears_its_alert() -> None:
    db = FakeSupabase()
    open_alert(db, minutes_ago=MIN_ALERT_AGE_MINUTES + 5)
    cell(db, rate=0.84, size=300)

    assert len(find_resolved_alerts(db)) == 1
    assert db.rows("network_alerts")[0]["resolved_at"] is not None


def test_a_still_degraded_instrument_keeps_its_alert() -> None:
    db = FakeSupabase()
    open_alert(db, minutes_ago=MIN_ALERT_AGE_MINUTES + 5)
    cell(db, rate=0.25, size=300)

    assert find_resolved_alerts(db) == []
    assert db.rows("network_alerts")[0]["resolved_at"] is None


def test_a_momentary_blink_back_does_not_clear_a_fresh_alert() -> None:
    """One good poll in the middle of an outage would unblock every retry into it."""
    db = FakeSupabase()
    open_alert(db, minutes_ago=2)
    cell(db, rate=0.90, size=300)

    assert find_resolved_alerts(db) == []


def test_silence_is_not_recovery() -> None:
    """An instrument nobody is retrying into may be one nobody *can* retry into."""
    db = FakeSupabase()
    open_alert(db, minutes_ago=MIN_ALERT_AGE_MINUTES + 5)

    assert find_resolved_alerts(db) == []
    assert db.rows("network_alerts")[0]["resolved_at"] is None


# ── The broadcast ──────────────────────────────────────────────────────


async def test_a_fired_alert_is_published_to_the_stream() -> None:
    db = FakeSupabase()
    degraded(db, rate=0.20)
    redis = FakeRedis()

    await detect_anomalies(db, redis)

    assert len(redis.published) == 1
    channel, payload = redis.published[0]
    assert channel == ALERTS_CHANNEL
    assert payload["type"] == "alert_fired"
    assert payload["alert"]["affected_bank"] == "SBI"


async def test_a_resolution_is_published_too() -> None:
    db = FakeSupabase()
    open_alert(db, minutes_ago=MIN_ALERT_AGE_MINUTES + 5)
    cell(db, rate=0.84, size=300)
    redis = FakeRedis()

    assert await resolve_stale_alerts(db, redis) == 1
    assert redis.published[0][1]["type"] == "alert_resolved"


async def test_a_broken_broadcast_does_not_lose_the_alert() -> None:
    """The row is what blocks retries; the push only updates a dashboard."""

    class BrokenRedis:
        async def publish(self, channel: str, payload: str) -> None:
            raise ConnectionError("redis is down")

    db = FakeSupabase()
    degraded(db, rate=0.20)

    assert len(await detect_anomalies(db, BrokenRedis())) == 1
    assert len(db.rows("network_alerts")) == 1


async def test_no_redis_at_all_is_not_an_error() -> None:
    db = FakeSupabase()
    degraded(db, rate=0.20)

    assert len(await detect_anomalies(db, None)) == 1
