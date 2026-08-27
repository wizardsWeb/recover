"""Health endpoints. Deliberately unauthenticated.

Two endpoints, answering two different questions:

``/health`` (liveness)
    "Is this process alive?" Answers from process state alone, touching
    nothing external. This is what the Container Apps liveness probe calls, and
    a liveness probe that depended on Supabase would turn a Supabase outage
    into a total one — Azure would kill every healthy replica, then fail to
    start their replacements for the same reason.

``/health/ready`` (readiness)
    "Can this process actually do its job?" Reaches Supabase. Intended for
    monitoring and for deciding whether to route traffic, not for deciding
    whether to kill anything.
"""

import asyncio

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.config import get_settings
from app.db import get_service_client
from app.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["health"])

#: Bounds how long a readiness probe can hang on a stalled connection. A probe
#: that never answers is worse than one that answers "not ready".
_PROBE_TIMEOUT_SECONDS = 5.0


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
    )


def _probe_supabase() -> None:
    """Cheapest possible round trip to Postgres, raising if it does not work.

    ``bandit_arms`` is global reference data — no tenant rows are read, so this
    stays safe to run under the service-role client.
    """
    client = get_service_client()
    client.table("bandit_arms").select("arm_name").limit(1).execute()


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    responses={503: {"description": "A dependency is unreachable."}},
)
async def ready() -> ReadinessResponse:
    try:
        # The Supabase client is synchronous. Called directly from an async
        # handler it would block the event loop for the whole round trip and
        # stall every other in-flight request on this worker.
        await asyncio.wait_for(
            run_in_threadpool(_probe_supabase),
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        # The real error goes to the logs, never to the response: this endpoint
        # is unauthenticated, and a driver error can carry a connection string.
        log.warning("health.ready.failed", dependency="supabase", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dependency unavailable: supabase",
        ) from exc

    return ReadinessResponse(status="ready", checks={"supabase": "ok"})
