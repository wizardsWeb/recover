"""The four paths through ``GeminiClient.generate_structured``.

The contract under test is not "Gemini answers correctly" — that is Google's
problem and it is not reproducible in CI. It is the promise the agent loop
depends on: **this function never raises, and it returns the caller's fallback
whenever it cannot return a real answer.** Every step in the loop is written
against that guarantee, so it gets tested directly rather than through a step.

httpx is mocked at the ``AsyncClient`` boundary, one layer below our own code
and one layer above the network. Patching ``generate_structured`` itself would
test nothing; letting it reach the real API would make the suite depend on a
quota and a key.
"""

import json
from typing import Any

import pytest

import app.agent.llm as llm_module
from app.agent.llm import DEFAULT_MODEL, GeminiClient, prompt_hash
from tests.simulator.fake_supabase import FakeSupabase

SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "verdict": {"type": "STRING"},
        "score": {"type": "NUMBER"},
    },
    "required": ["verdict", "score"],
}

FALLBACK: dict[str, Any] = {"verdict": "unknown", "score": 0.0}

ANSWER: dict[str, Any] = {"verdict": "salary_cycle_mismatch", "score": 0.82}


class _FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._body


class _FakeAsyncClient:
    """Stands in for ``httpx.AsyncClient``, counting the calls it receives."""

    calls: list[dict[str, Any]] = []

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        type(self).calls.append({"url": url, **kwargs})
        return _FakeResponse(
            {
                "candidates": [{"content": {"parts": [{"text": json.dumps(ANSWER)}]}}],
                "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 40},
            }
        )


class _ExplodingAsyncClient(_FakeAsyncClient):
    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        type(self).calls.append({"url": url})
        raise RuntimeError("502 Bad Gateway")


@pytest.fixture
def db() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture(autouse=True)
def reset_calls() -> None:
    _FakeAsyncClient.calls = []
    _ExplodingAsyncClient.calls = []


def _client(db: FakeSupabase, *, api_key: str | None = "test-key") -> GeminiClient:
    # No redis_url: the rate limiter is skipped entirely rather than degraded,
    # which is what the tests (and local development) want.
    return GeminiClient(db, api_key=api_key, redis_url=None)


async def test_cache_miss_calls_gemini_and_stores_the_response(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.agent.llm.httpx.AsyncClient", _FakeAsyncClient)

    result = await _client(db).generate_structured("why did this fail?", SCHEMA, "t", FALLBACK)

    assert result == ANSWER
    assert len(_FakeAsyncClient.calls) == 1

    rows = db.rows("llm_cache")
    assert len(rows) == 1
    assert rows[0]["prompt_hash"] == prompt_hash("t", "why did this fail?")
    assert rows[0]["response"] == ANSWER
    # The constant, not a literal: this asserts the model is recorded on the
    # row, and pinning the string here only means a model change fails a test
    # about caching.
    assert rows[0]["model"] == DEFAULT_MODEL
    assert rows[0]["input_tokens"] == 120
    assert rows[0]["output_tokens"] == 40
    # The preview is for debugging only — it must be the prompt, not the answer.
    assert rows[0]["prompt_preview"] == "why did this fail?"


async def test_cache_hit_skips_the_api_and_increments_hit_count(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.agent.llm.httpx.AsyncClient", _FakeAsyncClient)
    client = _client(db)

    first = await client.generate_structured("same prompt", SCHEMA, "t", FALLBACK)
    second = await client.generate_structured("same prompt", SCHEMA, "t", FALLBACK)

    assert first == second == ANSWER
    # The whole point: the second call cost nothing.
    assert len(_FakeAsyncClient.calls) == 1
    assert len(db.rows("llm_cache")) == 1
    assert db.rows("llm_cache")[0]["hit_count"] == 1


async def test_the_schema_name_is_part_of_the_cache_key(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same prompt under two schemas must not share a cached response."""
    monkeypatch.setattr("app.agent.llm.httpx.AsyncClient", _FakeAsyncClient)
    client = _client(db)

    await client.generate_structured("identical", SCHEMA, "diagnose", FALLBACK)
    await client.generate_structured("identical", SCHEMA, "listen", FALLBACK)

    assert len(_FakeAsyncClient.calls) == 2
    assert len(db.rows("llm_cache")) == 2


async def test_api_failure_returns_the_fallback_without_raising(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.agent.llm.httpx.AsyncClient", _ExplodingAsyncClient)

    result = await _client(db).generate_structured("anything", SCHEMA, "t", FALLBACK)

    # Identity, not equality: callers distinguish "the model answered" from
    # "the fallback came back" with `result is fallback`, so the exact object
    # has to come back, not a copy of it.
    assert result is FALLBACK
    assert len(_ExplodingAsyncClient.calls) == 1
    assert db.rows("llm_cache") == []


async def test_missing_api_key_returns_the_fallback_immediately(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.agent.llm.httpx.AsyncClient", _FakeAsyncClient)

    result = await _client(db, api_key=None).generate_structured("anything", SCHEMA, "t", FALLBACK)

    assert result is FALLBACK
    # "Immediately" is the assertion: no HTTP client is constructed and no cache
    # row is written, so an unconfigured deployment costs nothing per call.
    assert _FakeAsyncClient.calls == []
    assert db.rows("llm_cache") == []


async def test_response_missing_a_required_field_falls_back(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Structured output is reliable, not guaranteed — an off-schema answer is refused."""

    class _PartialClient(_FakeAsyncClient):
        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            type(self).calls.append({"url": url})
            return _FakeResponse(
                {"candidates": [{"content": {"parts": [{"text": json.dumps({"score": 0.4})}]}}]}
            )

    monkeypatch.setattr("app.agent.llm.httpx.AsyncClient", _PartialClient)

    result = await _client(db).generate_structured("anything", SCHEMA, "t", FALLBACK)

    assert result is FALLBACK
    # An answer we refused must not be cached, or the refusal becomes permanent.
    assert db.rows("llm_cache") == []


async def test_a_dead_cache_does_not_stop_the_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supabase being down degrades the cache, not the recovery."""

    class _DeadSupabase:
        def table(self, _name: str) -> Any:
            raise RuntimeError("connection refused")

    monkeypatch.setattr("app.agent.llm.httpx.AsyncClient", _FakeAsyncClient)

    client = GeminiClient(_DeadSupabase(), api_key="test-key", redis_url=None)
    result = await client.generate_structured("anything", SCHEMA, "t", FALLBACK)

    assert result == ANSWER
    assert len(_FakeAsyncClient.calls) == 1


async def test_the_api_key_travels_in_a_header_not_the_url(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A key in the query string lands in proxy logs and exception messages."""
    monkeypatch.setattr("app.agent.llm.httpx.AsyncClient", _FakeAsyncClient)

    await _client(db).generate_structured("anything", SCHEMA, "t", FALLBACK)

    call = _FakeAsyncClient.calls[0]
    assert "test-key" not in call["url"]
    assert call["headers"]["x-goog-api-key"] == "test-key"


async def test_a_transient_5xx_is_retried_then_falls_back(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bad moment at Google's end is worth a second try; a persistent one is not."""
    import httpx

    class _ServerErrorClient(_FakeAsyncClient):
        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            type(self).calls.append({"url": url})
            raise httpx.HTTPStatusError(
                "503",
                request=httpx.Request("POST", url),
                response=httpx.Response(503, request=httpx.Request("POST", url)),
            )

    monkeypatch.setattr("app.agent.llm.httpx.AsyncClient", _ServerErrorClient)

    result = await _client(db).generate_structured("anything", SCHEMA, "t", FALLBACK)

    assert result is FALLBACK
    assert len(_ServerErrorClient.calls) == llm_module._MAX_ATTEMPTS


async def test_a_4xx_is_not_retried(db: FakeSupabase, monkeypatch: pytest.MonkeyPatch) -> None:
    """A bad schema or a bad key fails identically every time — retrying only stalls."""
    import httpx

    class _BadRequestClient(_FakeAsyncClient):
        async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
            type(self).calls.append({"url": url})
            raise httpx.HTTPStatusError(
                "400",
                request=httpx.Request("POST", url),
                response=httpx.Response(400, request=httpx.Request("POST", url)),
            )

    monkeypatch.setattr("app.agent.llm.httpx.AsyncClient", _BadRequestClient)

    result = await _client(db).generate_structured("anything", SCHEMA, "t", FALLBACK)

    assert result is FALLBACK
    assert len(_BadRequestClient.calls) == 1
