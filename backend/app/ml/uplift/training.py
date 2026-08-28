"""Scheduling model retraining without getting in the loop's way.

Three hazards sit between "call train at the end of the pass" and something
safe to run in production, and each is handled here rather than at the call
site:

* **A bare ``create_task`` can be collected mid-run.** The event loop keeps only
  a weak reference to a task nobody holds, so a fire-and-forget training job can
  be garbage-collected part-way through. It does not raise; it simply stops, and
  the snapshot never appears. ``_IN_FLIGHT`` holds a strong reference until the
  task finishes.
* **Fitting is synchronous CPU work.** ``LogisticRegression.fit`` does not
  await, so running it on the event loop blocks every in-flight request for its
  duration. It goes to a worker thread.
* **A training failure must not reach the agent.** The loop has already done its
  job by the time this runs; a broken model is a degraded dashboard, not a lost
  recovery. Everything is swallowed and logged.

Retraining is also debounced. Fitting after every single case would spend most
of its time re-deriving the same coefficients from one extra row.
"""

import asyncio
from typing import Any, cast

from app.logging import get_logger
from app.ml.uplift.model import latest_snapshot, train_uplift_model

logger = get_logger(__name__)

#: Completed cases that must accumulate before a retrain is worth its cost.
MIN_NEW_CASES_BETWEEN_TRAINING = 20

#: Strong references to in-flight training tasks. Without this the event loop
#: holds only a weak reference and the task can be collected before it finishes.
_IN_FLIGHT: set[asyncio.Task[dict[str, Any] | None]] = set()


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], getattr(result, "data", None) or [])


def _closed_case_count(supabase_client: Any, merchant_id: str, playbook: str) -> int:
    rows = _rows(
        supabase_client.table("recovery_cases")
        .select("id, closed_at")
        .eq("merchant_id", merchant_id)
        .eq("playbook", playbook)
        .execute()
    )
    return sum(1 for row in rows if row.get("closed_at"))


def _should_retrain(supabase_client: Any, merchant_id: str, playbook: str) -> bool:
    """Whether enough has happened since the last snapshot to refit.

    Compared against the sample size the last snapshot was trained on, rather
    than against a timestamp: what makes a model stale is new outcomes, and a
    quiet week produces none.
    """
    snapshot = latest_snapshot(supabase_client, merchant_id, playbook)
    if snapshot is None:
        return True
    trained_on = int(snapshot.get("training_sample_size") or 0)
    return _closed_case_count(supabase_client, merchant_id, playbook) - trained_on >= (
        MIN_NEW_CASES_BETWEEN_TRAINING
    )


async def maybe_retrain_uplift_model(
    supabase_client: Any,
    merchant_id: str,
    playbook: str,
) -> dict[str, Any] | None:
    """Refit if enough new outcomes have landed, otherwise do nothing.

    Both the eligibility read and the fit run off the event loop: the read is a
    blocking HTTP call inside the Supabase client, and the fit is CPU-bound.
    """
    try:
        eligible = await asyncio.to_thread(_should_retrain, supabase_client, merchant_id, playbook)
        if not eligible:
            return None
        return await asyncio.to_thread(train_uplift_model, supabase_client, merchant_id, playbook)
    except Exception as exc:  # noqa: BLE001
        # A model that failed to train costs the dashboard its estimate. The
        # recovery this pass performed has already happened and must not be
        # undone by a reporting concern.
        logger.warning("uplift_retrain_error", playbook=playbook, error=str(exc))
        return None


def schedule_retrain(supabase_client: Any, merchant_id: str, playbook: str) -> None:
    """Fire a retrain in the background, if there is a loop to fire it into.

    Called at the end of the agent loop. Returns immediately — the pass is over
    and its result should not wait on a model refit.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — a synchronous caller, or a test driving the loop
        # directly. Training is a background nicety; skipping is correct.
        return

    task = loop.create_task(maybe_retrain_uplift_model(supabase_client, merchant_id, playbook))
    _IN_FLIGHT.add(task)
    task.add_done_callback(_IN_FLIGHT.discard)
