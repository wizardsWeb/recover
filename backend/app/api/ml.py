"""Model training control plane.

One endpoint, and it exists because training is otherwise invisible. The agent
loop retrains on its own once enough outcomes accumulate, which is the right
behaviour in production and a poor one in a demo: seeding two hundred cases and
then waiting for a threshold nobody can see is not a thing anyone can present.

Unlike the simulator router this is **not** gated to development. Training reads
the merchant's own closed cases through their own RLS-scoped client and writes a
snapshot for them — there is nothing here a merchant should not be able to do to
their own data, and a real deployment benefits from being able to force a refit
after a backfill.

Being ungated makes the cost of the work the endpoint's problem. Fitting is
CPU-bound sklearn, and the default request fits four playbooks, so two things are
enforced here that the background path in ``app.ml.uplift.training`` already gets
for free:

* **The fit runs in a worker thread.** ``LogisticRegression.fit`` never awaits, so
  calling it in the handler would park the event loop — and with it every other
  request on the process — for the duration of four fits.
* **One training run per merchant at a time.** A thread pool is finite. Without a
  guard, a held button or a retrying client turns one authenticated caller into
  enough queued fits to starve the pool for everyone.
"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.agent.playbooks import PLAYBOOK_CONFIGS
from app.deps import CurrentUserId, UserSupabase
from app.logging import get_logger
from app.ml.uplift.model import train_uplift_model

log = get_logger(__name__)

router = APIRouter(prefix="/api/ml", tags=["ml"])

#: Merchants with a training run in flight. Concurrent requests are rejected
#: rather than queued: the second run would read the same rows and write the same
#: snapshot, so waiting for it buys nothing and costs a worker thread.
_TRAINING: set[str] = set()


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TrainRequest(CamelModel):
    #: Omitted means every playbook — the usual case after seeding.
    playbook: str | None = Field(default=None)


class TrainedPlaybook(CamelModel):
    playbook: str
    status: str
    treated_samples: int = 0
    control_samples: int = 0
    mean_cate: float | None = None
    min_samples: int | None = None


class TrainResponse(CamelModel):
    results: list[TrainedPlaybook]


@router.post("/uplift/train", response_model=TrainResponse)
async def train_uplift(
    payload: TrainRequest,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> TrainResponse:
    """Fit the uplift model now, for one playbook or all four.

    A playbook without enough data is reported as `insufficient_data` rather
    than failing the request. Training all four when only one has history is the
    normal case, and a 500 for the other three would make a working call look
    broken.
    """
    if user_id in _TRAINING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A training run is already in progress for this merchant.",
        )

    targets = [payload.playbook] if payload.playbook else list(PLAYBOOK_CONFIGS)

    results: list[TrainedPlaybook] = []
    _TRAINING.add(user_id)
    try:
        for playbook in targets:
            outcome: dict[str, Any] = await asyncio.to_thread(
                train_uplift_model, supabase, user_id, str(playbook)
            )
            results.append(
                TrainedPlaybook(
                    playbook=str(playbook),
                    status=str(outcome.get("status")),
                    treated_samples=int(outcome.get("treated_samples") or 0),
                    control_samples=int(outcome.get("control_samples") or 0),
                    mean_cate=outcome.get("mean_cate"),
                    min_samples=outcome.get("min_samples"),
                )
            )
    finally:
        _TRAINING.discard(user_id)

    log.info(
        "uplift_training_requested",
        merchant_id=user_id,
        playbooks=[r.playbook for r in results],
        statuses=[r.status for r in results],
    )
    return TrainResponse(results=results)
