"""The loop that must not be able to die.

A stopped poller is the worst failure in this subsystem and the hardest to see:
nothing clears a network alert except this loop, and the guardrail blocks
retries while one is open. So a poller that dies leaves every merchant
permanently unable to retry into a bank that recovered hours ago — with no
error, no alert, and no symptom except recovery quietly not happening.

These tests are almost entirely about that.
"""

import asyncio
from typing import Any

import pytest

from app.ml.network import poller as module
from app.ml.network.poller import run_network_poll, run_network_poller
from tests.simulator.fake_supabase import FakeSupabase


def boom(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("stage exploded")


async def async_boom(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("stage exploded")


# ── One pass ───────────────────────────────────────────────────────────


async def test_a_pass_reports_what_each_stage_did(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "aggregate_network_stats", lambda *a, **k: 7)

    async def two_alerts(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"id": "a"}, {"id": "b"}]

    async def one_resolved(*args: Any, **kwargs: Any) -> int:
        return 1

    monkeypatch.setattr(module, "detect_anomalies", two_alerts)
    monkeypatch.setattr(module, "resolve_stale_alerts", one_resolved)

    assert await run_network_poll(FakeSupabase()) == {
        "stats_upserted": 7,
        "alerts_fired": 2,
        "alerts_resolved": 1,
    }


@pytest.mark.parametrize(
    ("name", "replacement"),
    [
        ("aggregate_network_stats", boom),
        ("detect_anomalies", async_boom),
        ("resolve_stale_alerts", async_boom),
    ],
)
async def test_one_broken_stage_does_not_take_the_others_down(
    monkeypatch: pytest.MonkeyPatch, name: str, replacement: Any
) -> None:
    """A failed stage costs its own result for one pass, and nothing else."""
    monkeypatch.setattr(module, name, replacement)

    summary = await run_network_poll(FakeSupabase())

    assert (
        summary[
            {
                "aggregate_network_stats": "stats_upserted",
                "detect_anomalies": "alerts_fired",
                "resolve_stale_alerts": "alerts_resolved",
            }[name]
        ]
        == 0
    )


async def test_the_stages_run_in_dependency_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """Detecting against stats this pass did not refresh tests a stale reading.

    Resolving before detecting is worse: it would clear an alert using the very
    numbers that are about to re-fire it.
    """
    order: list[str] = []
    monkeypatch.setattr(
        module, "aggregate_network_stats", lambda *a, **k: order.append("aggregate") or 0
    )

    async def detect(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        order.append("detect")
        return []

    async def resolve(*args: Any, **kwargs: Any) -> int:
        order.append("resolve")
        return 0

    monkeypatch.setattr(module, "detect_anomalies", detect)
    monkeypatch.setattr(module, "resolve_stale_alerts", resolve)

    await run_network_poll(FakeSupabase())

    assert order == ["aggregate", "detect", "resolve"]


async def test_aggregation_does_not_run_on_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It is blocking Supabase I/O over thousands of rows."""
    import threading

    seen: list[str] = []
    monkeypatch.setattr(
        module,
        "aggregate_network_stats",
        lambda *a, **k: seen.append(threading.current_thread().name) or 0,
    )

    await run_network_poll(FakeSupabase())

    assert seen and "MainThread" not in seen[0]


# ── The loop ───────────────────────────────────────────────────────────


async def test_a_failing_pass_does_not_stop_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """The property the whole module exists for.

    Nothing but this loop clears a network alert, and the guardrail blocks
    retries while one is open.
    """
    passes = 0

    async def sometimes_explodes(*args: Any, **kwargs: Any) -> dict[str, int]:
        nonlocal passes
        passes += 1
        raise RuntimeError("the whole pass exploded")

    monkeypatch.setattr(module, "run_network_poll", sometimes_explodes)

    task = asyncio.create_task(run_network_poller(FakeSupabase(), None, interval_seconds=0))
    while passes < 3:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert passes >= 3


async def test_cancellation_stops_the_loop_rather_than_being_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown is not a failure. Swallowing it would hang the process."""

    async def noop(*args: Any, **kwargs: Any) -> dict[str, int]:
        return {}

    monkeypatch.setattr(module, "run_network_poll", noop)

    task = asyncio.create_task(run_network_poller(FakeSupabase(), None, interval_seconds=0))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()


async def test_the_first_poll_waits_for_the_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    """Several replicas rolling at once must not all aggregate the same window."""
    passes = 0

    async def count(*args: Any, **kwargs: Any) -> dict[str, int]:
        nonlocal passes
        passes += 1
        return {}

    monkeypatch.setattr(module, "run_network_poll", count)

    task = asyncio.create_task(run_network_poller(FakeSupabase(), None, interval_seconds=3600))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert passes == 0
