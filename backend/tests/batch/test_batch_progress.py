"""Progress, as seen by a browser subscribed to the run's row.

The row is both the progress channel and the result store, which is the point:
one record to subscribe to, and no window in which a status endpoint and a
result endpoint disagree about what happened. What that costs is that `result`
changes shape partway through, so the frontend has to distinguish a partial
`{progress: ...}` object from a finished `BatchResult`. These tests pin the
difference.
"""

from typing import Any

import pytest

from app.simulator import batch as module
from app.simulator.batch import PROGRESS_EVERY, run_batch
from tests.simulator.fake_supabase import FakeSupabase

MERCHANT = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.rows("batch_runs").append(
        {"id": "run-1", "merchant_id": MERCHANT, "status": "running", "result": None}
    )
    return fake


def progress(db: FakeSupabase) -> dict[str, Any]:
    return db.rows("batch_runs")[0]["result"]


async def test_progress_carries_enough_to_draw_the_bar_and_the_lines(
    db: FakeSupabase,
) -> None:
    """A percentage alone would leave the chart empty until the run finished.

    The whole point of the running state is watching the two traces build, so
    the series so far travels with each tick.
    """
    await run_batch(db, MERCHANT, n_cases=300, seed=1, batch_id="run-1", persist_cases=False)

    body = progress(db)
    assert body["progress"] == {"cases_done": 300, "total": 300, "pct": 1.0}
    assert body["current_bandit_rate"] is not None
    assert body["current_baseline_rate"] is not None
    assert len(body["time_series"]) == 300 // module.WINDOW


async def test_progress_is_written_at_the_stated_interval(db: FakeSupabase) -> None:
    """Every case would be a thousand round trips to move a progress bar."""
    seen: list[int] = []
    original = module._write_progress

    def capture(client: Any, batch_id: str, done: int, total: int, series: Any) -> None:
        seen.append(done)
        original(client, batch_id, done, total, series)

    module._write_progress = capture
    try:
        await run_batch(db, MERCHANT, n_cases=500, seed=1, batch_id="run-1", persist_cases=False)
    finally:
        module._write_progress = original

    assert seen == [100, 200, 300, 400, 500]
    assert all(done % PROGRESS_EVERY == 0 for done in seen)


async def test_a_run_with_no_batch_id_writes_no_progress(db: FakeSupabase) -> None:
    """Calibration runs want the numbers, not a row to update."""
    await run_batch(db, MERCHANT, n_cases=300, seed=1, persist_cases=False)

    assert progress(db) is None


async def test_a_failed_progress_write_does_not_stop_the_run(db: FakeSupabase) -> None:
    """A dropped tick costs the bar a jump. Losing the run costs the result."""

    class Broken(FakeSupabase):
        def table(self, name: str) -> Any:
            if name == "batch_runs":
                raise ConnectionError("update failed")
            return super().table(name)

    result = await run_batch(
        Broken(), MERCHANT, n_cases=300, seed=1, batch_id="run-1", persist_cases=False
    )

    assert result.total_cases == 300


async def test_the_partial_and_the_final_result_are_tellable_apart(db: FakeSupabase) -> None:
    """The frontend branches on this, so the shapes must not overlap.

    A partial has `progress` and no `total_cases`; the finished result is the
    other way round. Anything ambiguous would have the page render a completed
    run as a stalled progress bar, or the reverse.
    """
    await run_batch(db, MERCHANT, n_cases=200, seed=1, batch_id="run-1", persist_cases=False)
    partial = progress(db)

    assert "progress" in partial
    assert "total_cases" not in partial

    final = (await run_batch(None, MERCHANT, n_cases=200, seed=1, persist_cases=False)).to_dict()
    assert "progress" not in final
    assert "total_cases" in final
