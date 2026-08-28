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
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.agent.playbooks import PLAYBOOK_CONFIGS
from app.deps import CurrentUserId, UserSupabase
from app.logging import get_logger
from app.ml.uplift.model import train_uplift_model

log = get_logger(__name__)

router = APIRouter(prefix="/api/ml", tags=["ml"])


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
    targets = [payload.playbook] if payload.playbook else list(PLAYBOOK_CONFIGS)

    results: list[TrainedPlaybook] = []
    for playbook in targets:
        outcome: dict[str, Any] = train_uplift_model(supabase, user_id, str(playbook))
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

    log.info(
        "uplift_training_requested",
        merchant_id=user_id,
        playbooks=[r.playbook for r in results],
        statuses=[r.status for r in results],
    )
    return TrainResponse(results=results)
