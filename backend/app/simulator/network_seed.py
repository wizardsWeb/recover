"""A week of plausible Indian payment behaviour, manufactured.

The heatmap's whole claim is that *when* matters — that HDFC cards at 10am and
HDFC cards at 11pm are different instruments wearing the same name. A grid
seeded from uniform noise would render as static and make that claim look like
decoration, so the generator below encodes the shapes the claim is about:

* **A daily arc.** Every instrument does better in business hours than at 3am.
  Batch windows, staffing, and the customers still awake are all different.
* **Per-bank character.** HDFC cards collapse late at night; ICICI UPI sags on
  the 1st, when salary timing and mandate presentation collide; PAYTM's wallet
  runs consistently lower than a bank rail; AXIS is unremarkable, which is
  itself worth showing — not every row is a story.
* **A few real incidents.** SBI UPI carries two historical degradations. They
  are what give the detector's baseline something to have recovered from, and
  what make a live outage look like a recurrence rather than a novelty.

Sample sizes follow volume, not the rate: a 4am cell has tens of retries and a
noon cell has hundreds. That is what makes the "indicative — thin samples"
watermark and the detector's `MIN_ALERT_SAMPLES` floor mean anything, because a
grid where every cell had 300 retries would never exercise either.

Rows go in through the same shape the aggregator writes, so the heatmap, the
detector and the resolver all read one kind of row. A seeder with its own row
shape demos beautifully and diverges at the first real poll.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.logging import get_logger
from app.ml.network.aggregator import IST

logger = get_logger(__name__)

DEFAULT_DAYS = 7
MAX_DAYS = 14

#: Rows per insert.
_CHUNK = 200


@dataclass(frozen=True)
class Instrument:
    """One bank/method rail, and how it behaves across a day."""

    bank: str
    method: str
    #: Mean success rate across a whole day.
    base_rate: float
    #: Multiplier per IST hour, applied to `base_rate`. Length 24.
    hourly: tuple[float, ...]
    #: Share of the network's retry volume that lands on this rail.
    volume_share: float
    #: Rate multiplier on the 1st of the month. Salary timing pushes a month's
    #: worth of mandates into one morning.
    first_of_month: float = 1.0


def _arc(
    *,
    night: float = 0.72,
    morning: float = 1.08,
    midday: float = 1.05,
    evening: float = 0.98,
    late: float = 0.85,
) -> tuple[float, ...]:
    """A day's shape as 24 multipliers.

    Named bands rather than a formula: the boundaries are the ones `_period` in
    the bandit's context vector already uses, so the two agree about when
    morning is.
    """
    shape: list[float] = []
    for hour in range(24):
        if 0 <= hour < 6:
            shape.append(night)
        elif 6 <= hour < 12:
            shape.append(morning)
        elif 12 <= hour < 17:
            shape.append(midday)
        elif 17 <= hour < 21:
            shape.append(evening)
        else:
            shape.append(late)
    return tuple(shape)


INSTRUMENTS: tuple[Instrument, ...] = (
    # The finding the heatmap exists to show: a 34-point spread between 9am and
    # 11pm on the same rail.
    Instrument(
        bank="HDFC",
        method="card",
        base_rate=0.78,
        hourly=_arc(night=0.62, morning=1.06, midday=1.02, evening=0.94, late=0.44),
        volume_share=0.26,
    ),
    Instrument(
        bank="HDFC",
        method="upi",
        base_rate=0.81,
        hourly=_arc(),
        volume_share=0.10,
    ),
    # Sags on the 1st: mandate presentation and salary credit land the same day.
    Instrument(
        bank="ICICI",
        method="upi",
        base_rate=0.84,
        hourly=_arc(night=0.80, morning=1.06, midday=1.04),
        volume_share=0.22,
        first_of_month=0.74,
    ),
    Instrument(
        bank="SBI",
        method="upi",
        base_rate=0.79,
        hourly=_arc(night=0.74, morning=1.05),
        volume_share=0.18,
    ),
    Instrument(
        bank="SBI",
        method="netbanking",
        base_rate=0.68,
        hourly=_arc(night=0.60, late=0.70),
        volume_share=0.06,
    ),
    # Unremarkable, and shown anyway. Not every row is a story, and a grid where
    # all five banks had a finding would be a grid nobody believed.
    Instrument(
        bank="AXIS",
        method="card",
        base_rate=0.76,
        hourly=_arc(night=0.88, morning=1.04, midday=1.02, evening=1.0, late=0.92),
        volume_share=0.10,
    ),
    Instrument(
        bank="PAYTM",
        method="wallet",
        base_rate=0.71,
        hourly=_arc(night=0.86, morning=1.04),
        volume_share=0.08,
    ),
)

#: Retries the whole network sees in one hour, by IST hour. Peaks late morning,
#: bottoms out overnight.
_HOURLY_VOLUME: tuple[int, ...] = (
    120,
    80,
    55,
    40,
    40,
    70,  # 00-05
    180,
    340,
    620,
    900,
    1150,
    1200,  # 06-11
    1050,
    900,
    820,
    780,
    740,  # 12-16
    700,
    640,
    560,
    480,  # 17-20
    380,
    260,
    180,  # 21-23
)

#: Historical incidents: `(bank, method, days_ago, first_hour, last_hour, rate)`.
#: Two of them, on the rail the B3 demo takes down, so a live outage reads as a
#: recurrence with a baseline to recover to rather than a first-ever event.
_INCIDENTS: tuple[tuple[str, str, int, int, int, float], ...] = (
    ("SBI", "upi", 5, 14, 18, 0.31),
    ("SBI", "upi", 2, 21, 23, 0.44),
)


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], getattr(result, "data", None) or [])


def _incident_rate(bank: str, method: str, days_ago: int, hour: int) -> float | None:
    for inc_bank, inc_method, inc_days, first, last, rate in _INCIDENTS:
        if (
            inc_bank == bank
            and inc_method == method
            and inc_days == days_ago
            and first <= hour <= last
        ):
            return rate
    return None


def _clear_window(supabase_client: Any, since: datetime) -> int:
    """Drop existing readings in the window being replaced.

    Re-seeding is the normal demo action, and without this a second run leaves
    two readings per cell — the heatmap would show whichever sorted first, and
    the baseline would average a seeded week against itself.

    This deletes real aggregated rows too. That is correct here and only here:
    the endpoint is gated to development, where the only rows in the window are
    ones a previous seed or a local poller put there.
    """
    deleted = _rows(
        supabase_client.table("network_stats")
        .delete()
        .gte("window_end", since.isoformat())
        .execute()
    )
    return len(deleted)


def seed_network_stats(
    supabase_client: Any,
    *,
    days: int = DEFAULT_DAYS,
    seed: int | None = None,
) -> dict[str, Any]:
    """Write `days` of hourly readings for every instrument.

    Takes the **service-role** client: `network_stats` has no merchant column
    and no RLS policy that a user client would satisfy.

    `seed` fixes the draw, so a rehearsed demo shows the same heatmap twice.
    """
    rng = random.Random(seed)
    now = datetime.now(UTC)
    now_ist = now.astimezone(IST)
    since = now - timedelta(days=days)

    cleared = _clear_window(supabase_client, since)

    payload: list[dict[str, Any]] = []
    for days_ago in range(days):
        day_ist = now_ist - timedelta(days=days_ago)
        for hour in range(24):
            moment = day_ist.replace(hour=hour, minute=50, second=0, microsecond=0)
            if moment > now_ist:
                # Today's later hours have not happened. Seeding them would put
                # readings in the future and hand the detector a "current" cell
                # that has not occurred.
                continue

            for instrument in INSTRUMENTS:
                rate = _incident_rate(instrument.bank, instrument.method, days_ago, hour)
                if rate is None:
                    rate = instrument.base_rate * instrument.hourly[hour]
                    if moment.day == 1:
                        rate *= instrument.first_of_month
                    # A few points of noise, so no two days are identical and
                    # the detector has a real spread to compute a z-score over.
                    rate += rng.uniform(-0.035, 0.035)

                volume = _HOURLY_VOLUME[hour] * instrument.volume_share
                sample_size = max(8, int(rng.uniform(0.75, 1.25) * volume))

                window_end = moment.astimezone(UTC)
                payload.append(
                    {
                        "bank": instrument.bank,
                        "method": instrument.method,
                        "hour_of_day": hour,
                        "day_of_week": moment.weekday(),
                        "success_rate": round(min(0.99, max(0.02, rate)), 3),
                        "sample_size": sample_size,
                        "window_start": (window_end - timedelta(minutes=10)).isoformat(),
                        "window_end": window_end.isoformat(),
                    }
                )

    for start in range(0, len(payload), _CHUNK):
        supabase_client.table("network_stats").insert(payload[start : start + _CHUNK]).execute()

    logger.info(
        "network_stats_seeded",
        rows=len(payload),
        cleared=cleared,
        days=days,
        instruments=len(INSTRUMENTS),
    )
    return {
        "rows": len(payload),
        "cleared": cleared,
        "days": days,
        "instruments": len(INSTRUMENTS),
        "banks": sorted({instrument.bank for instrument in INSTRUMENTS}),
        "methods": sorted({instrument.method for instrument in INSTRUMENTS}),
    }
