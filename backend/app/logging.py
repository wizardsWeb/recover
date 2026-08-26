"""Structured logging setup.

Every log line is JSON so Azure Container Apps (and `docker compose logs`) can
parse it without a regex. ``trace_id`` is bound per request by the middleware in
``app.main``, which means every line emitted while handling a request carries it
without any call site having to pass it along.
"""

import logging
import sys

import structlog

from app.config import get_settings


def configure_logging() -> None:
    """Configure stdlib logging and structlog to emit JSON to stdout."""
    settings = get_settings()
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for ``name``."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
