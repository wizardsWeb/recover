"""The network intelligence surface.

Everything here reads pooled, cross-merchant aggregates, which makes it the one
router where the usual guarantee — RLS scopes the query to the caller — does not
apply. What replaces it is that **there is nothing per-merchant left to scope**.
`network_stats` and `network_alerts` hold no merchant column at all; the closest
thing is an alert's `affected_merchants_count`, and a cardinality identifies
nobody. So these endpoints read through the caller's own client anyway, and the
absence of tenant data is a property of the schema rather than of a filter
someone has to remember to write.

The exception is `/benchmark`, which is per-merchant by definition. It reads the
caller's own recovery rate through their RLS-scoped client and the peer
distribution through the service-role one, then returns three summary statistics
and a percentile — so the caller sees their own number and the shape of everyone
else's, never anyone else's number. That distinction collapses when the peer
group is small enough to name, which is what `MIN_PEER_MERCHANTS` is for.

**The WebSocket takes its token in the query string.** Browsers cannot set an
`Authorization` header on a WebSocket handshake; that is a limitation of the API,
not a decision made here. The token is verified with the same
`verify_supabase_jwt` the HTTP dependencies use, before the socket is accepted,
and an unverifiable one is closed rather than served. The stream carries only
network-wide alerts — the same rows `/alerts` returns to any authenticated
caller — so a leaked query-string token exposes nothing this endpoint would not
have told its holder anyway.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import statistics
import time
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.auth import verify_supabase_jwt
from app.db import get_redis_client, get_service_client
from app.deps import CurrentUserId, UserSupabase
from app.logging import get_logger
from app.ml.network.aggregator import normalise_bank, normalise_method
from app.ml.network.detector import ALERTS_CHANNEL

log = get_logger(__name__)

router = APIRouter(prefix="/api/network", tags=["network"])

#: The banks the heatmap always draws a row for, in order. Fixed rather than
#: derived from the data: a bank that saw no traffic today is a blank row, and a
#: grid that silently drops it looks like a smaller network rather than a quiet
#: bank.
HEATMAP_BANKS = ("HDFC", "ICICI", "SBI", "AXIS", "PAYTM")

HOURS = tuple(range(24))

#: Below this a cell is drawn as provisional. The frontend renders a "simulated
#: data" watermark when most cells are under it.
THIN_CELL_SAMPLES = 10

#: How far back the heatmap looks for a cell's most recent reading.
HEATMAP_LOOKBACK_DAYS = 7

#: How far back `/alerts` reports resolved alerts.
RECENT_ALERT_HOURS = 24

#: Peers required before a distribution is reported. With one other merchant the
#: median is that merchant's recovery rate, and calling it "the vertical median"
#: does not make it less of a disclosure.
MIN_PEER_MERCHANTS = 5

#: Closed cases a peer needs before it counts. Below this a merchant's rate is
#: 0% or 100% and pulls the median to an edge it does not belong at.
MIN_PEER_CASES = 5

_MAX_ROWS = 5000

#: Seconds between WebSocket keepalives. Load balancers and reverse proxies
#: close an idle upgrade well before this in most default configurations, and a
#: quiet network is the normal state — the whole product goal is that alerts are
#: rare — so without a heartbeat the healthy case is the one that disconnects.
HEARTBEAT_SECONDS = 30

#: How long one poll of the pub/sub channel waits before looping. Short so an
#: alert reaches the browser promptly, and it is the floor on the loop's own
#: cycle time rather than the heartbeat's — the two are deliberately separate,
#: because a client that returns from `get_message` early must not turn into a
#: keepalive every microsecond.
_POLL_SECONDS = 1.0


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], getattr(result, "data", None) or [])


# ── Heatmap ────────────────────────────────────────────────────────────


@router.get("/heatmap")
async def get_heatmap(
    user_id: CurrentUserId,
    supabase: UserSupabase,
    method: str | None = Query(default=None),
) -> dict[str, Any]:
    """Success rate per bank per hour, most recent reading per cell.

    One cell is *the latest measurement* for that `(bank, method, hour)`, not an
    average over the week. A mean would smooth an outage into invisibility — the
    grid exists to show that SBI's 3pm is wrong right now, and an average with
    six healthy days in it would render that cell green.
    """
    since = (datetime.now(UTC) - timedelta(days=HEATMAP_LOOKBACK_DAYS)).isoformat()
    query = (
        supabase.table("network_stats")
        .select("bank, method, hour_of_day, success_rate, sample_size, window_end")
        .gte("window_end", since)
        .order("window_end", desc=True)
        .limit(_MAX_ROWS)
    )
    if method:
        query = query.eq("method", normalise_method(method))

    latest: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in _rows(query.execute()):
        try:
            hour = int(row.get("hour_of_day") or 0)
        except (TypeError, ValueError):
            continue
        key = (normalise_bank(row.get("bank")), normalise_method(row.get("method")), hour)
        # Newest first, so the first row seen for a cell is the one to draw.
        latest.setdefault(key, row)

    cells: list[dict[str, Any]] = []
    thin = 0
    for (bank, cell_method, hour), row in sorted(latest.items()):
        sample_size = int(row.get("sample_size") or 0)
        thin += sample_size < THIN_CELL_SAMPLES
        cells.append(
            {
                "bank": bank,
                "method": cell_method,
                "hour": hour,
                "success_rate": float(row.get("success_rate") or 0.0),
                "sample_size": sample_size,
            }
        )

    return {
        "banks": list(HEATMAP_BANKS),
        "hours": list(HOURS),
        "methods": sorted({str(cell["method"]) for cell in cells}),
        "cells": cells,
        # Not an error state. A merchant in week one has a legitimately empty
        # grid, and saying so beats rendering 120 grey squares with no
        # explanation.
        "is_sparse": bool(cells) and thin > len(cells) / 2,
        "note": (
            "No network statistics yet — run the simulator's network seeder to populate the grid."
            if not cells
            else None
        ),
    }


# ── Alerts ─────────────────────────────────────────────────────────────


def _alert(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "alert_type": row.get("alert_type"),
        "bank": row.get("affected_bank"),
        "method": row.get("affected_method"),
        "severity": row.get("severity"),
        "z_score": row.get("z_score"),
        "sample_size": row.get("sample_size"),
        "affected_merchants_count": row.get("affected_merchants_count"),
        "network_wide_success_rate": row.get("network_wide_success_rate"),
        "baseline_rate": row.get("baseline_rate"),
        "detected_at": row.get("detected_at"),
        "resolved_at": row.get("resolved_at"),
    }


@router.get("/alerts")
async def get_alerts(user_id: CurrentUserId, supabase: UserSupabase) -> dict[str, Any]:
    """Open alerts, plus the ones that closed in the last day.

    Recent-but-resolved matter as much as open ones: they are what makes an
    empty banner trustworthy. "All banks healthy" reads very differently beside
    "SBI UPI recovered 40 minutes ago" than it does alone.
    """
    since = (datetime.now(UTC) - timedelta(hours=RECENT_ALERT_HOURS)).isoformat()
    rows = _rows(
        supabase.table("network_alerts")
        .select("*")
        .gte("detected_at", since)
        .order("detected_at", desc=True)
        .limit(_MAX_ROWS)
        .execute()
    )

    # Open alerts are fetched without the time filter: an outage that started
    # two days ago and is still open is the single most important thing on this
    # page, and a 24-hour window would hide exactly that case.
    open_rows = _rows(
        supabase.table("network_alerts")
        .select("*")
        .is_("resolved_at", "null")
        .order("detected_at", desc=True)
        .limit(_MAX_ROWS)
        .execute()
    )

    active = [_alert(row) for row in open_rows]
    recent = [_alert(row) for row in rows if row.get("resolved_at")]

    return {
        "active": active,
        "recent": recent,
        "total_active": len(active),
        "checked_at": datetime.now(UTC).isoformat(),
    }


# ── Benchmark ──────────────────────────────────────────────────────────


def _recovery_rate(cases: list[dict[str, Any]]) -> float | None:
    closed = [case for case in cases if case.get("closed_at")]
    if not closed:
        return None
    recovered = sum(1 for case in closed if int(case.get("amount_recovered_cents") or 0) > 0)
    return recovered / len(closed)


@router.get("/benchmark")
async def get_benchmark(user_id: CurrentUserId, supabase: UserSupabase) -> dict[str, Any]:
    """Where this merchant's recovery rate sits against the rest of the network.

    Two reads with two different clients, and the split is the whole point.

    The caller's own rate comes through their RLS-scoped client, so it is their
    number by construction. The peer distribution comes through the service-role
    client, because computing a median across merchants is precisely the
    cross-tenant work RLS is there to prevent — and it is exactly the kind this
    product exists to do. What makes that safe is not a filter but the shape of
    what is returned: three summary statistics and a percentile. No merchant id,
    no per-merchant rate, nothing that can be inverted back to a row.

    That last part stops being true when the peer group is small enough to
    identify. With one other merchant the median *is* their rate. So a
    distribution is only reported once `MIN_PEER_MERCHANTS` of them exist; below
    that the response says the network is too small rather than quietly handing
    over a competitor's recovery rate wearing the word "median".
    """
    own = _rows(
        supabase.table("recovery_cases")
        .select("closed_at, amount_recovered_cents")
        .eq("merchant_id", user_id)
        # Batch-simulated cases are excluded here and in the peer read below.
        # Left in, a merchant who ran a demo would jump the percentile on
        # invented recoveries, and everyone else's rank would move with it.
        .is_("metadata->>is_batch_synthetic", "null")
        .limit(_MAX_ROWS)
        .execute()
    )
    merchant_rate = _recovery_rate(own)
    closed_count = sum(1 for case in own if case.get("closed_at"))

    if merchant_rate is None:
        return {
            "merchant_rate": None,
            "vertical_median": None,
            "vertical_top_decile": None,
            "percentile": None,
            "sample_size": 0,
            "peer_merchants": 0,
            "basis": "no_closed_cases",
        }

    peers = _peer_rates(user_id)
    if len(peers) < MIN_PEER_MERCHANTS:
        return {
            "merchant_rate": round(merchant_rate, 4),
            "vertical_median": None,
            "vertical_top_decile": None,
            "percentile": None,
            "sample_size": closed_count,
            "peer_merchants": len(peers),
            # Named so the UI states the limitation instead of rendering a
            # blank where a comparison should be.
            "basis": "network_too_small",
        }

    ranked = sorted(peers)
    below = sum(1 for rate in ranked if rate < merchant_rate)

    return {
        "merchant_rate": round(merchant_rate, 4),
        "vertical_median": round(statistics.median(ranked), 4),
        "vertical_top_decile": round(_quantile(ranked, 0.9), 4),
        "percentile": round(100 * below / len(ranked)),
        "sample_size": closed_count,
        "peer_merchants": len(peers),
        "basis": "network",
    }


def _quantile(ranked: list[float], fraction: float) -> float:
    """Nearest-rank quantile over an already-sorted list.

    Nearest-rank rather than interpolated: an interpolated top decile over a
    handful of merchants invents a value that no merchant achieved, and this
    number is shown to people as something to aim at.
    """
    if not ranked:
        return 0.0
    index = min(len(ranked) - 1, max(0, int(round(fraction * (len(ranked) - 1)))))
    return ranked[index]


def _peer_rates(exclude_merchant_id: str) -> list[float]:
    """Every other merchant's recovery rate, as bare numbers.

    Deliberately returns a list of floats and not rows: the merchant ids are
    dropped inside this function, so no caller further up can accidentally put
    one in a response. Failures return an empty list — a benchmark is a nice to
    have, and the caller's own rate is still worth rendering without it.
    """
    try:
        rows = _rows(
            get_service_client()
            .table("recovery_cases")
            .select("merchant_id, closed_at, amount_recovered_cents")
            .is_("metadata->>is_batch_synthetic", "null")
            .limit(_MAX_ROWS)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("network_benchmark_peer_read_error", error=str(exc))
        return []

    by_merchant: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        merchant = str(row.get("merchant_id") or "")
        if not merchant or merchant == exclude_merchant_id:
            continue
        by_merchant.setdefault(merchant, []).append(row)

    return [
        rate
        for cases in by_merchant.values()
        # A merchant with a handful of closed cases has a recovery "rate" of
        # 0% or 100% and would drag the median to an edge.
        if len(cases) >= MIN_PEER_CASES and (rate := _recovery_rate(cases)) is not None
    ]


# ── Live stream ────────────────────────────────────────────────────────


async def _authenticate(websocket: WebSocket, token: str | None) -> str | None:
    """Verify before accepting. Returns the user id, or closes and returns None."""
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")
        return None
    try:
        return str(verify_supabase_jwt(token)["sub"])
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return None


@router.websocket("/alerts/stream")
async def stream_alerts(websocket: WebSocket, token: str | None = Query(default=None)) -> None:
    """Push network alerts as they are detected.

    The subscription is torn down in a `finally`. A pub/sub connection that
    outlives its socket is not merely a leak: Redis goes on delivering to it, so
    a server that has been open for a week accumulates one dead subscriber per
    dropped browser tab and spends real work fanning out to none of them.

    A heartbeat goes out every `HEARTBEAT_SECONDS` whether or not anything has
    happened. Silence here means the network is healthy — the desirable state —
    so without it the proxy would close the connection precisely when the
    product is working, and the dashboard would go stale without saying so.
    """
    user_id = await _authenticate(websocket, token)
    if user_id is None:
        return

    await websocket.accept()
    redis_client = get_redis_client()
    pubsub = redis_client.pubsub()

    try:
        await pubsub.subscribe(ALERTS_CHANNEL)
        await websocket.send_json({"type": "connected", "channel": ALERTS_CHANNEL})

        last_beat = time.monotonic()
        while True:
            started = time.monotonic()
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=_POLL_SECONDS
            )

            if message is None:
                # Not every client honours the timeout — `fakeredis` returns
                # immediately — and a loop that trusted it would spin a core on
                # an idle socket. Sleeping the remainder makes the cycle time a
                # property of this loop rather than of the client underneath it.
                elapsed = time.monotonic() - started
                if elapsed < _POLL_SECONDS:
                    await asyncio.sleep(_POLL_SECONDS - elapsed)

                if time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
                    await websocket.send_json(
                        {"type": "heartbeat", "at": datetime.now(UTC).isoformat()}
                    )
                    last_beat = time.monotonic()
                continue

            data = message.get("data")
            try:
                payload = json.loads(data if isinstance(data, str) else data.decode())
            except (ValueError, AttributeError, UnicodeDecodeError):
                log.warning("network_stream_unreadable_message")
                continue
            await websocket.send_json(payload)

    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("network_stream_error", error=str(exc))
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(ALERTS_CHANNEL)
        with contextlib.suppress(Exception):
            await pubsub.aclose()  # type: ignore[no-untyped-call]
