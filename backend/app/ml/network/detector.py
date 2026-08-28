"""Deciding when a bank has actually gone wrong.

The detector is a rolling z-score against the same cell's own history: how many
standard errors below its usual rate is this bank/method/hour right now? That
framing is what makes the threshold portable — a five-point drop is noise for a
cell that sees forty retries an hour and an emergency for one that sees four
hundred, and a z-score already knows the difference.

**Two conditions, both required.** A z-score alone fires on statistically
certain trivia: with a large enough sample, a drop from 84% to 81% clears any
threshold you like and means nothing to a merchant. So a drop must also be
materially large in absolute terms. Requiring both is what keeps an alert
something worth interrupting someone for.

**An alert is an action, not a notification.** The guardrail blocks retries on an
open alert, so a false positive stops real recovery attempts across every
merchant on the network. That asymmetry is why the thresholds sit where they do,
why a thin sample is skipped outright rather than estimated, and why the
resolution path is checked as carefully as the detection one — an alert that
fires correctly and then never clears does the same damage more slowly.
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.logging import get_logger
from app.ml.network.aggregator import (
    RETRY_ACTION,
    get_historical_baseline,
    normalise_bank,
    normalise_method,
)

logger = get_logger(__name__)

#: The Redis channel the WebSocket stream subscribes to.
ALERTS_CHANNEL = "network:alerts"

#: Below this a z-score is arithmetic on noise. Higher than the aggregator's
#: storage floor on purpose: a cell worth keeping for tomorrow's baseline is not
#: yet a cell worth blocking every merchant's retries on today.
MIN_ALERT_SAMPLES = 10

#: Standard errors below baseline before a drop is considered real.
Z_THRESHOLD = -2.5

#: And the drop must be this large in absolute terms. Without it, a big enough
#: sample makes an 84%-to-81% dip statistically undeniable and operationally
#: meaningless.
MIN_ABSOLUTE_DROP = 0.15

#: z-score boundaries, worst first. Order matters — the first match wins.
_SEVERITY_BANDS: tuple[tuple[float, str], ...] = (
    (-3.5, "critical"),
    (-3.0, "high"),
    (Z_THRESHOLD, "medium"),
)

#: An alert younger than this is not eligible to resolve. A bank that blinks
#: back for one poll in the middle of an outage would otherwise clear the alert
#: and unblock every retry into it.
MIN_ALERT_AGE_MINUTES = 30

#: How close to baseline counts as recovered.
RECOVERY_TOLERANCE = 0.05

#: How far back to look for the reading being tested. Two hours, so a cell that
#: has gone quiet does not silently reuse yesterday's number as "current".
CURRENT_WINDOW_HOURS = 2

_MAX_ROWS = 5000


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], getattr(result, "data", None) or [])


def z_score(current_rate: float, baseline_rate: float, sample_size: int) -> float:
    """Standard errors between the observed rate and its baseline.

    The standard error is the binomial one under the *baseline* proportion,
    which is the null hypothesis being tested — using the observed proportion
    instead would let a catastrophic reading shrink its own error bar and look
    less surprising the worse it got.

    The baseline is clamped away from 0 and 1 because the error there is
    genuinely zero, and dividing by it would report an infinite z for a
    one-attempt fluctuation.
    """
    if sample_size <= 0:
        return 0.0
    safe = min(max(baseline_rate, 0.01), 0.99)
    standard_error = math.sqrt(safe * (1.0 - safe) / sample_size)
    if standard_error == 0.0:
        return 0.0
    return (current_rate - baseline_rate) / standard_error


def severity_for(z: float) -> str | None:
    """The band this z-score falls in, or None if it is not an anomaly."""
    for boundary, label in _SEVERITY_BANDS:
        if z < boundary:
            return label
    return None


def _recent_cells(supabase_client: Any) -> list[dict[str, Any]]:
    """The most recent reading per `(bank, method)` within the current window."""
    since = (datetime.now(UTC) - timedelta(hours=CURRENT_WINDOW_HOURS)).isoformat()
    rows = _rows(
        supabase_client.table("network_stats")
        .select("bank, method, hour_of_day, success_rate, sample_size, window_end")
        .gte("window_end", since)
        .order("window_end", desc=True)
        .limit(_MAX_ROWS)
        .execute()
    )

    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (normalise_bank(row.get("bank")), normalise_method(row.get("method")))
        # Rows arrive newest-first, so the first one seen for a pair is the one
        # to test. Later rows are that cell's older readings.
        latest.setdefault(key, row)
    return list(latest.values())


def _open_alert_keys(supabase_client: Any) -> set[tuple[str, str]]:
    """`(bank, method)` pairs that already have an unresolved alert."""
    rows = _rows(
        supabase_client.table("network_alerts")
        .select("affected_bank, affected_method, resolved_at")
        .is_("resolved_at", "null")
        .limit(_MAX_ROWS)
        .execute()
    )
    return {
        (normalise_bank(row.get("affected_bank")), normalise_method(row.get("affected_method")))
        for row in rows
    }


def _affected_merchant_count(supabase_client: Any, bank: str, method: str) -> int:
    """How many merchants retried into this instrument recently.

    Counted here rather than carried on the stats row: `network_stats` stores an
    aggregate and deliberately holds no merchant identifiers, so the count is
    derived at alert time from the raw attempts and only its *cardinality* is
    ever stored. It is what turns "SBI UPI is degraded" into "and it is hitting
    eight of you", which is the sentence that makes a network product worth
    joining.
    """
    since = (datetime.now(UTC) - timedelta(hours=CURRENT_WINDOW_HOURS)).isoformat()
    rows = _rows(
        supabase_client.table("execution_attempts")
        .select("merchant_id, action_type, request_payload, attempted_at")
        .gte("attempted_at", since)
        .limit(_MAX_ROWS)
        .execute()
    )
    merchants = {
        str(row["merchant_id"])
        for row in rows
        if str(row.get("action_type")) == RETRY_ACTION
        and isinstance(row.get("request_payload"), dict)
        and normalise_bank(row["request_payload"].get("bank")) == bank
        and normalise_method(row["request_payload"].get("method")) == method
        and row.get("merchant_id")
    }
    return len(merchants)


def find_anomalies(supabase_client: Any) -> list[dict[str, Any]]:
    """Test every recent cell and write an alert row for each degradation.

    Synchronous, and takes the **service-role** client: it reads across every
    merchant. Returns the alert rows it inserted, which the async wrapper
    publishes. Splitting it this way keeps the blocking Supabase work in one
    place that a worker thread can hold.
    """
    open_keys = _open_alert_keys(supabase_client)
    fired: list[dict[str, Any]] = []

    for cell in _recent_cells(supabase_client):
        bank = normalise_bank(cell.get("bank"))
        method = normalise_method(cell.get("method"))
        if (bank, method) in open_keys:
            # Already alerting. Re-firing would spam the stream and reset the
            # 30-minute resolution clock on every poll, so an outage would never
            # be old enough to clear.
            continue

        try:
            sample_size = int(cell.get("sample_size") or 0)
            current_rate = float(cell.get("success_rate") or 0.0)
            hour = int(cell.get("hour_of_day") or 0)
        except (TypeError, ValueError):
            continue
        if sample_size < MIN_ALERT_SAMPLES:
            continue

        baseline = get_historical_baseline(supabase_client, bank, method, hour)
        z = z_score(current_rate, baseline, sample_size)
        severity = severity_for(z)
        if severity is None or current_rate >= baseline - MIN_ABSOLUTE_DROP:
            continue

        alert = {
            "alert_type": "degradation",
            "affected_bank": bank,
            "affected_method": method,
            "severity": severity,
            "z_score": round(z, 3),
            "sample_size": sample_size,
            "affected_merchants_count": _affected_merchant_count(supabase_client, bank, method),
            "network_wide_success_rate": round(current_rate, 3),
            "baseline_rate": round(baseline, 3),
            "detected_at": datetime.now(UTC).isoformat(),
            "resolved_at": None,
            "metadata": {"hour_of_day": hour, "source": "z_score_detector"},
        }
        written = _rows(supabase_client.table("network_alerts").insert(alert).execute())
        fired.append(written[0] if written else alert)
        logger.warning(
            "network_alert_fired",
            bank=bank,
            method=method,
            severity=severity,
            z_score=round(z, 3),
            current_rate=current_rate,
            baseline_rate=round(baseline, 3),
        )

    return fired


def find_resolved_alerts(supabase_client: Any) -> list[dict[str, Any]]:
    """Clear alerts whose instrument has come back. Returns the rows cleared."""
    cutoff = (datetime.now(UTC) - timedelta(minutes=MIN_ALERT_AGE_MINUTES)).isoformat()
    open_alerts = [
        row
        for row in _rows(
            supabase_client.table("network_alerts")
            .select(
                "id, affected_bank, affected_method, baseline_rate, detected_at, "
                "severity, metadata"
            )
            .is_("resolved_at", "null")
            .limit(_MAX_ROWS)
            .execute()
        )
        if str(row.get("detected_at") or "") <= cutoff
    ]
    if not open_alerts:
        return []

    current = {
        (normalise_bank(cell.get("bank")), normalise_method(cell.get("method"))): cell
        for cell in _recent_cells(supabase_client)
    }

    resolved: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()
    for alert in open_alerts:
        bank = normalise_bank(alert.get("affected_bank"))
        method = normalise_method(alert.get("affected_method"))
        cell = current.get((bank, method))
        if cell is None:
            # No recent reading at all. Silence is not recovery — an instrument
            # nobody is retrying into may be one nobody can retry into, so the
            # alert stands until something is actually observed.
            continue

        try:
            rate = float(cell.get("success_rate") or 0.0)
            baseline = float(alert.get("baseline_rate") or 0.0)
        except (TypeError, ValueError):
            continue
        if rate < baseline - RECOVERY_TOLERANCE:
            continue

        supabase_client.table("network_alerts").update(
            {"resolved_at": now, "updated_at": now}
        ).eq("id", alert["id"]).execute()
        resolved.append({**alert, "resolved_at": now, "recovered_rate": round(rate, 3)})
        logger.info(
            "network_alert_resolved", bank=bank, method=method, recovered_rate=round(rate, 3)
        )

    return resolved


async def publish_alert(redis_client: Any, payload: dict[str, Any]) -> None:
    """Push one event onto the alerts channel.

    Never raises. A dashboard that missed a push is a stale dashboard; an
    exception here would take down the poll that also does the blocking, which
    is the part that actually protects merchants.
    """
    if redis_client is None:
        return
    try:
        await redis_client.publish(ALERTS_CHANNEL, json.dumps(payload, default=str))
    except Exception as exc:  # noqa: BLE001
        logger.warning("network_alert_publish_error", error=str(exc))


async def detect_anomalies(supabase_client: Any, redis_client: Any = None) -> list[dict[str, Any]]:
    """Find degradations, record them, and broadcast each one.

    The database work runs off the event loop; only the publish awaits.
    """
    fired = await asyncio.to_thread(find_anomalies, supabase_client)
    for alert in fired:
        await publish_alert(redis_client, {"type": "alert_fired", "alert": alert})
    return fired


async def resolve_stale_alerts(supabase_client: Any, redis_client: Any = None) -> int:
    """Clear recovered alerts and broadcast the recovery. Returns how many."""
    resolved = await asyncio.to_thread(find_resolved_alerts, supabase_client)
    for alert in resolved:
        await publish_alert(redis_client, {"type": "alert_resolved", "alert": alert})
    return len(resolved)
