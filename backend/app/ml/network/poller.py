"""The loop that keeps the network view current.

Three jobs, in order, once a minute: pool the last window of retries, test every
cell for degradation, and clear alerts whose instrument has come back. Order
matters — detecting against stats this pass did not refresh would test a bank
against a reading from a minute ago, and resolving before detecting would clear
an alert using the same numbers that were about to re-fire it.

**This loop must not be able to die.** The guardrail blocks retries on an open
alert and nothing else clears one, so a poller that stops leaves every merchant
permanently blocked from retrying into a bank that recovered hours ago. The
failure would be invisible: no error, no alert, just recovery quietly not
happening. So every stage is independently wrapped, a failed stage costs only
its own result for one pass, and the loop's own `except` catches anything the
stages did not.

`asyncio.CancelledError` is the one exception that is re-raised. It is not a
failure — it is shutdown asking, and swallowing it would hang the process.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.logging import get_logger
from app.ml.network.aggregator import aggregate_network_stats
from app.ml.network.detector import detect_anomalies, resolve_stale_alerts

logger = get_logger(__name__)

DEFAULT_INTERVAL_SECONDS = 60


async def run_network_poll(supabase_client: Any, redis_client: Any = None) -> dict[str, int]:
    """One pass. Each stage fails alone; the pass always returns a summary.

    Split out from the loop so it can be called directly — by a test, or by
    anything that wants a synchronous refresh without waiting for the next tick.
    """
    summary = {"stats_upserted": 0, "alerts_fired": 0, "alerts_resolved": 0}

    try:
        # Aggregation is blocking Supabase I/O; the detector does its own
        # threading, so only this call needs moving off the loop here.
        summary["stats_upserted"] = await asyncio.to_thread(
            aggregate_network_stats, supabase_client
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("network_aggregate_error", error=str(exc))

    try:
        summary["alerts_fired"] = len(await detect_anomalies(supabase_client, redis_client))
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("network_detect_error", error=str(exc))

    try:
        summary["alerts_resolved"] = await resolve_stale_alerts(supabase_client, redis_client)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        # The stage whose failure is least visible and most expensive: an alert
        # that never clears goes on blocking retries into a healthy bank.
        logger.warning("network_resolve_error", error=str(exc))

    logger.info("network_poll_complete", **summary)
    return summary


async def run_network_poller(
    supabase_client: Any,
    redis_client: Any = None,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Poll forever. Returns only on cancellation.

    The sleep comes first. A poll on startup would run before the process is
    serving traffic and, in a deployment that rolls several replicas at once,
    would have every one of them aggregating the same window simultaneously.
    """
    logger.info("network_poller_started", interval_seconds=interval_seconds)
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await run_network_poll(supabase_client, redis_client)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                # Belt and braces. `run_network_poll` already contains its
                # stages, so reaching here means something outside them broke —
                # and the loop still has to survive it.
                logger.warning("network_poll_error", error=str(exc))
    except asyncio.CancelledError:
        logger.info("network_poller_stopped")
        raise
