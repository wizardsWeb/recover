"""FastAPI application entrypoint."""

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.api import (
    analytics,
    audit,
    cases,
    events,
    health,
    integrations,
    merchants,
    ml,
    network,
    playbooks,
    simulator,
)
from app.config import get_settings
from app.db import get_redis_client, get_service_client
from app.logging import configure_logging, get_logger
from app.ml.network.poller import run_network_poller

configure_logging()
log = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Own the background network poller for the life of the process.

    The task handle is held in a local rather than fired and forgotten: the
    event loop keeps only a weak reference to a task nobody holds, so a
    fire-and-forget poller can be garbage-collected mid-pass — silently, since
    it does not raise. It simply stops, and nothing clears a network alert
    again.

    Cancellation on shutdown is awaited rather than merely requested. Without
    the await the process can exit while the poller is mid-write, leaving a
    half-aggregated window behind.
    """
    if not settings.NETWORK_POLLER_ENABLED:
        log.info("network_poller_disabled", environment=settings.ENVIRONMENT)
        yield
        return

    task = asyncio.create_task(
        run_network_poller(
            get_service_client(),
            get_redis_client(),
            interval_seconds=settings.NETWORK_POLL_INTERVAL_SECONDS,
        )
    )
    log.info(
        "network_poller_scheduled",
        interval_seconds=settings.NETWORK_POLL_INTERVAL_SECONDS,
        # Says out loud which Redis is in play: an in-process fake reaches only
        # subscribers in this worker, which is correct on a laptop and wrong
        # anywhere with more than one replica.
        redis="configured" if settings.REDIS_URL.strip() else "in-process fake",
    )
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Recover API",
    description="AI revenue-recovery agent for Razorpay merchants.",
    version=settings.VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def trace_requests(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Bind a trace id to the logging context for the life of the request.

    An inbound ``X-Trace-Id`` is honoured so a trace can be followed from the
    browser through to the agent's audit trail; otherwise one is generated. The
    id goes back out on the response so the client can log it too.
    """
    trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        trace_id=trace_id,
        method=request.method,
        path=request.url.path,
    )

    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)

    log.info("http.request", status_code=response.status_code, duration_ms=duration_ms)
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Render HTTP errors in the same shape as everything else."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"message": exc.detail, "status": exc.status_code}},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return 422s with the same envelope, plus the offending fields."""
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "message": "Request validation failed",
                "status": 422,
                "details": exc.errors(),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log the traceback, return an opaque 500 — never leak internals to a client."""
    log.exception("http.unhandled_error", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": {"message": "Internal server error", "status": 500}},
    )


app.include_router(health.router)
app.include_router(merchants.router)
app.include_router(events.router)
app.include_router(cases.router)
app.include_router(playbooks.router)
app.include_router(audit.router)
app.include_router(analytics.router)
app.include_router(ml.router)
app.include_router(network.router)
app.include_router(integrations.router)
# The simulator router refuses to serve outside a development environment;
# see the dependency on `require_dev_environment`.
app.include_router(simulator.router)
