"""Test fixtures.

The settings object requires real Supabase values, so they are stubbed into the
environment *before* ``app.main`` is imported. Phase 1 tests exercise routing
and the auth boundary only — nothing here talks to a live database.
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
