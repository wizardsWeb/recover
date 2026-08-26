"""FastAPI application entrypoint."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.api import health, merchants, simulator
from app.config import get_settings
from app.logging import configure_logging, get_logger

configure_logging()
log = get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="Recover API",
    description="AI revenue-recovery agent for Razorpay merchants.",
    version=settings.VERSION,
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
# The simulator router refuses to serve outside a development environment;
# see the dependency on `require_dev_environment`.
app.include_router(simulator.router)
