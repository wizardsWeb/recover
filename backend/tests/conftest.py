"""Test fixtures.

The settings object requires real Supabase values, so they are stubbed into the
environment *before* ``app.main`` is imported. Phase 1 tests exercise routing
and the auth boundary only — nothing here talks to a live database.

Two background behaviours are disabled suite-wide.

**Uplift retraining.** The loop schedules a refit on completion. It runs in a
worker thread against the in-memory Supabase fake, which is a plain dict of
lists with no locking, so a test asserting on rows while a training thread
appends to them is a race — and one that would surface as an occasional,
unreproducible failure rather than a clear one. Scheduling is covered by tests
that call it directly.

**Holdout assignment** is disabled for the same reason it is random. It is a genuine random draw, so
leaving it live would send roughly one case in twenty down the control path and
fail whichever assertion happened to be looking — a test that goes red once a
fortnight, on a different test each time. Holdout behaviour is covered by tests
that pin the draw explicitly rather than by tests that happen to hit it.
"""

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("VERSION", "0.1.0")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def no_holdout_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every case is treated unless a test asks otherwise.

    The draw is replaced rather than the rate, so a test that wants a holdout
    can override this fixture by patching ``holdout.draw`` back to a value
    under the rate, and still exercise the real threshold comparison.
    """
    from app.agent import holdout

    monkeypatch.setattr(holdout, "draw", lambda: 1.0)


@pytest.fixture(autouse=True)
def no_background_retraining(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep model fitting off the test event loop.

    The scheduler is exercised directly in `tests/agent/test_uplift_training`;
    what is suppressed here is the loop firing it as a side effect of every
    other test in the suite.
    """
    from app.agent import core

    monkeypatch.setattr(core, "schedule_retrain", lambda *args, **kwargs: None)
