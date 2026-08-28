"""Pooling retry outcomes across every merchant into `network_stats`.

One merchant's view of a bank is too small to act on. Four failed UPI retries in
ten minutes is a Tuesday; four hundred across the network is an outage. This
module is what turns the first into the second, and the anomaly detector next
door is what decides when to say so.

**Two signals, pooled.** The primary is `execution_attempts` — a retry either
succeeded or it did not, which is exactly the Bernoulli trial the rate wants.
The secondary is `bandit_rewards`, whose binary reward records whether a case
recovered after the arm was pulled. That is a noisier proxy for instrument
health (a customer can pay through a different route), so it is pooled into the
same counts rather than averaged separately: successes and trials add, which is
the only combination that keeps the result a genuine rate.

**Row shape.** A row is *the most recent measurement in one clock hour* for one
`(bank, method, hour, day-of-week)` cell, not a running total over the hour.
`window_start`/`window_end` are that measurement's real bounds, so a reader can
always tell how much time the sample covers. Repeated polls inside the same hour
overwrite; a new hour inserts. Without that, a 60-second poller writing a
10-minute window would leave six overlapping rows an hour and the baseline would
be counting the same retries repeatedly.

Hours are IST throughout. The whole thesis of the time dimension — that a bank's
9am is not its 11pm — is about a person's day, and a UTC hour column would smear
that across five and a half hours of the wrong ones.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from app.logging import get_logger

logger = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")

#: Only retries. A WhatsApp send says nothing about whether a bank can settle a
#: charge, and mixing the two would make the rate track message volume.
RETRY_ACTION = "retry_charge"

#: Below this a cell is one bad customer, not a signal. It is deliberately lower
#: than the detector's own floor: a cell worth *storing* for tomorrow's baseline
#: is not yet a cell worth *alerting* on today.
MIN_CELL_SAMPLES = 5

#: What a bank's success rate is assumed to be with no history at all. Roughly
#: the Indian card/UPI retry success rate, and deliberately not 1.0 — a default
#: of "everything always works" would make the first real degradation look
#: catastrophic and the first quiet hour look like an outage.
DEFAULT_BASELINE_RATE = 0.75

#: How far back a baseline looks. Long enough to average out a bad afternoon,
#: short enough that a bank which genuinely got worse last month is not being
#: compared against a version of itself that no longer exists.
BASELINE_LOOKBACK_DAYS = 7

#: Rows to pull per read. The aggregator runs on a short window, so this is a
#: ceiling against a pathological backlog rather than an expected page size.
_MAX_ROWS = 5000


@dataclass
class _Cell:
    """Running tally for one `(bank, method, hour, day)` cell."""

    successes: float = 0.0
    trials: float = 0.0
    #: Distinct merchants that contributed. Never leaves this module as a set —
    #: only its length reaches an alert, and only to say how wide an outage is.
    merchants: set[str] = field(default_factory=set)

    @property
    def success_rate(self) -> float:
        return self.successes / self.trials if self.trials else 0.0


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], getattr(result, "data", None) or [])


def normalise_bank(raw: Any) -> str:
    """Uppercase, trimmed. Empty becomes `UNKNOWN`.

    The guardrail looks up alerts with `bank.upper()`, so an alert stored in any
    other case is an alert that never blocks anything — the failure is silent,
    and the retry goes out into a bank that is down.
    """
    text = str(raw or "").strip().upper()
    return text or "UNKNOWN"


def normalise_method(raw: Any) -> str:
    """Lowercase, trimmed. Empty becomes `unknown`. Mirrors the guardrail's `.lower()`."""
    text = str(raw or "").strip().lower()
    return text or "unknown"


def _ist(stamp: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(IST)


def _hour_floor(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def _tally_attempts(
    rows: list[dict[str, Any]], cells: dict[tuple[str, str, int, int], _Cell]
) -> None:
    """Fold `execution_attempts` into cells: a success is a success."""
    for row in rows:
        if str(row.get("action_type")) != RETRY_ACTION:
            continue
        payload = row.get("request_payload")
        if not isinstance(payload, dict):
            continue
        moment = _ist(row.get("attempted_at"))
        if moment is None:
            continue

        key = (
            normalise_bank(payload.get("bank")),
            normalise_method(payload.get("method")),
            moment.hour,
            moment.weekday(),
        )
        cell = cells[key]
        cell.trials += 1.0
        if str(row.get("status")) == "success":
            cell.successes += 1.0
        merchant = row.get("merchant_id")
        if merchant:
            cell.merchants.add(str(merchant))


def _tally_rewards(
    rows: list[dict[str, Any]], cells: dict[tuple[str, str, int, int], _Cell]
) -> None:
    """Fold `bandit_rewards` in as a second, weaker trial per case.

    The reward is whether the case recovered, which is downstream of the
    instrument working — a customer who pays by a different route counts as a
    win here and tells us nothing about the bank. Pooling it as one more trial
    rather than averaging it in keeps that dilution proportional to how much of
    it there is, instead of letting a handful of rewards outvote a hundred
    attempts.
    """
    for row in rows:
        context = row.get("context_vector")
        if not isinstance(context, dict):
            continue
        moment = _ist(row.get("observed_at"))
        if moment is None:
            continue
        try:
            reward = float(row.get("reward_value") or 0.0)
        except (TypeError, ValueError):
            continue

        key = (
            normalise_bank(context.get("bank")),
            normalise_method(context.get("method")),
            moment.hour,
            moment.weekday(),
        )
        cell = cells[key]
        cell.trials += 1.0
        cell.successes += max(0.0, min(1.0, reward))
        merchant = row.get("merchant_id")
        if merchant:
            cell.merchants.add(str(merchant))


def _write_cell(
    supabase_client: Any,
    key: tuple[str, str, int, int],
    cell: _Cell,
    window_start: datetime,
    window_end: datetime,
) -> None:
    """Insert this cell's measurement, or replace this hour's if one exists.

    Select-then-write rather than PostgREST's `upsert`: `network_stats` has no
    unique constraint to resolve a conflict against, and adding one on
    `(bank, method, hour_of_day, day_of_week)` would collapse this week's
    Tuesday onto last week's — which is precisely the history the baseline is
    made of.
    """
    bank, method, hour, day = key
    payload = {
        "bank": bank,
        "method": method,
        "hour_of_day": hour,
        "day_of_week": day,
        "success_rate": round(cell.success_rate, 3),
        "sample_size": int(round(cell.trials)),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "updated_at": window_end.isoformat(),
    }

    existing = _rows(
        supabase_client.table("network_stats")
        .select("id, window_start")
        .eq("bank", bank)
        .eq("method", method)
        .eq("hour_of_day", hour)
        .eq("day_of_week", day)
        .gte("window_start", _hour_floor(window_end).isoformat())
        .limit(1)
        .execute()
    )
    if existing:
        supabase_client.table("network_stats").update(payload).eq("id", existing[0]["id"]).execute()
    else:
        supabase_client.table("network_stats").insert(payload).execute()


def aggregate_network_stats(supabase_client: Any, window_minutes: int = 10) -> int:
    """Pool the last `window_minutes` of retries into `network_stats`.

    Takes the **service-role** client. This reads every merchant's attempts, so
    it cannot run under RLS — and for the same reason nothing it returns
    identifies a merchant. The return value is a count of cells written.

    Synchronous: the Supabase client blocks on HTTP, so this belongs in a worker
    thread. The poller is what puts it there.
    """
    now = datetime.now(UTC)
    window_start = now - timedelta(minutes=window_minutes)

    cells: dict[tuple[str, str, int, int], _Cell] = defaultdict(_Cell)

    attempts = _rows(
        supabase_client.table("execution_attempts")
        .select("merchant_id, action_type, status, request_payload, attempted_at")
        .gte("attempted_at", window_start.isoformat())
        .limit(_MAX_ROWS)
        .execute()
    )
    _tally_attempts(attempts, cells)

    rewards = _rows(
        supabase_client.table("bandit_rewards")
        .select("merchant_id, context_vector, reward_value, observed_at")
        .gte("observed_at", window_start.isoformat())
        .limit(_MAX_ROWS)
        .execute()
    )
    _tally_rewards(rewards, cells)

    written = 0
    for key, cell in cells.items():
        if cell.trials < MIN_CELL_SAMPLES:
            continue
        if key[0] == "UNKNOWN" or key[1] == "unknown":
            # A cell nobody can act on. The guardrail looks alerts up by a real
            # bank and method, so an UNKNOWN row can only ever dilute a baseline.
            continue
        _write_cell(supabase_client, key, cell, window_start, now)
        written += 1

    logger.info(
        "network_stats_aggregated",
        cells_written=written,
        cells_seen=len(cells),
        attempts=len(attempts),
        rewards=len(rewards),
        window_minutes=window_minutes,
    )
    return written


def get_historical_baseline(
    supabase_client: Any,
    bank: str,
    method: str,
    hour_of_day: int,
) -> float:
    """This cell's normal success rate, from the past week.

    Weighted by `sample_size`, so a quiet 3am hour with eleven attempts does not
    carry the same weight as a 10am hour with four hundred.

    **The current clock hour is excluded.** The aggregator writes this hour's
    reading moments before the detector asks for its baseline, so including it
    would let the measurement vote on what counts as normal — the baseline would
    drift towards every anomaly and the z-score would shrink to meet it. What is
    wanted is the same hour on previous days, which is exactly what is left.

    Falls back to `DEFAULT_BASELINE_RATE` with no history, which makes the first
    week's detections conservative rather than absent.
    """
    now = datetime.now(UTC)
    since = (now - timedelta(days=BASELINE_LOOKBACK_DAYS)).isoformat()
    try:
        rows = _rows(
            supabase_client.table("network_stats")
            .select("success_rate, sample_size, window_end")
            .eq("bank", normalise_bank(bank))
            .eq("method", normalise_method(method))
            .eq("hour_of_day", hour_of_day)
            .gte("window_end", since)
            .lt("window_end", _hour_floor(now).isoformat())
            .limit(_MAX_ROWS)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 - no history is a valid state
        logger.warning("network_baseline_fetch_error", bank=bank, error=str(exc))
        return DEFAULT_BASELINE_RATE

    weighted = 0.0
    total = 0.0
    for row in rows:
        try:
            size = float(row.get("sample_size") or 0)
            rate = float(row.get("success_rate") or 0.0)
        except (TypeError, ValueError):
            continue
        if size <= 0:
            continue
        weighted += rate * size
        total += size

    return weighted / total if total > 0 else DEFAULT_BASELINE_RATE
