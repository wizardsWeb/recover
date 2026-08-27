"""Health endpoints — liveness and readiness."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import health


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["version"] == "0.1.0"


def test_health_does_not_touch_supabase(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Liveness must answer from process state alone.

    This is what the Container Apps liveness probe calls. If it depended on
    Supabase, a Supabase outage would have Azure kill every healthy replica and
    then fail to start their replacements.
    """

    def explode() -> Any:
        raise AssertionError("liveness must not build a Supabase client")

    monkeypatch.setattr(health, "get_service_client", explode)

    assert client.get("/health").status_code == 200


class _StubQuery:
    """The fluent chain a Supabase select goes through."""

    def __init__(self, on_execute: Any) -> None:
        self._on_execute = on_execute

    def select(self, *_: Any, **__: Any) -> "_StubQuery":
        return self

    def limit(self, *_: Any, **__: Any) -> "_StubQuery":
        return self

    def execute(self) -> Any:
        return self._on_execute()


class _StubClient:
    def __init__(self, on_execute: Any) -> None:
        self._on_execute = on_execute

    def table(self, *_: Any, **__: Any) -> _StubQuery:
        return _StubQuery(self._on_execute)


def test_ready_returns_200_when_supabase_answers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        health, "get_service_client", lambda: _StubClient(lambda: {"data": []})
    )

    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["supabase"] == "ok"


def test_ready_returns_503_when_supabase_is_unreachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable() -> Any:
        raise ConnectionError("name or service not known")

    monkeypatch.setattr(health, "get_service_client", lambda: _StubClient(unreachable))

    response = client.get("/health/ready")

    assert response.status_code == 503
    # The standard error envelope, same as everything else in the API.
    assert response.json()["error"]["status"] == 503


def test_ready_does_not_leak_the_underlying_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A readiness probe is unauthenticated, so its body is public."""

    def unreachable() -> Any:
        raise ConnectionError("postgres://user:hunter2@db.internal:5432 refused")

    monkeypatch.setattr(health, "get_service_client", lambda: _StubClient(unreachable))

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert "hunter2" not in response.text
