"""Gemini client for the three steps that need a model.

Three call sites — diagnose, message generation, listen classification — share
one entry point, ``GeminiClient.generate_structured``. It takes a prompt, a
Gemini JSON schema, and a **fallback dict**, and it returns a dict. That is the
whole contract, and the important half of it is the fallback:

    ``generate_structured`` never raises.

Every failure mode — no API key, HTTP error, malformed JSON, a response missing
a required field, a dead Redis, a dead Supabase — is logged and answered with
the caller's fallback. The agent loop runs as a background task with no caller
to surface an exception to, and a Gemini outage must degrade the reasoning, not
end the recovery. Each step keeps its pre-LLM behaviour as that fallback, so the
worst case is exactly Phase 4.

Three layers sit in front of the API call, in order:

``cache``
    ``llm_cache`` keyed by ``sha256(schema_name + prompt)``. Salting the hash
    with the schema name is what stops a diagnose response ever being served to
    a message call — same context, different shape. A hit increments
    ``hit_count`` and returns without touching the network, which is what makes
    the demo reproducible and free.

``rate limiter``
    A Redis token bucket, 12 requests/minute, sized to the Gemini free tier. It
    **fails open**: if Redis is unreachable the call proceeds. A missing limiter
    costs quota; a limiter that blocks because its own dependency died costs the
    demo. The refill-and-consume is a Lua script because ``GET`` then ``SET``
    from Python is a read-modify-write race — two concurrent agent loops would
    both read the same token count and both spend it.

``schema validation``
    The response is checked against the schema's own top-level ``required``
    list. Gemini's structured-output mode is reliable, not guaranteed, and a
    response missing ``root_cause`` would otherwise reach a ``KeyError`` three
    frames deeper with no context.

Temperature is 0.2 throughout. These are extraction and classification calls,
not creative ones — the same case should diagnose the same way twice, and a
cached response is only honest if the uncached one would have matched it.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.logging import get_logger

logger = get_logger(__name__)

#: Free-tier flash model. Named here rather than in settings because the prompt
#: templates are written against this model's structured-output behaviour.
#:
#: Pinned to a stable release, not an alias. ``gemini-2.0-flash-exp`` used to be
#: here and was retired, which every call then met as a 404 — and because the
#: error path returns the fallback, nothing looked broken. The app went on
#: serving canned copy in place of generated text, indefinitely and quietly.
#: ``gemini-flash-latest`` would have the same failure shape on the day its
#: contents change under a rehearsed demo, so the version stays explicit.
DEFAULT_MODEL = "gemini-2.5-flash"

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

#: Low, because every call here is extraction or classification. See module docstring.
DEFAULT_TEMPERATURE = 0.2

#: Gemini free tier allows 15 RPM; 12 leaves headroom for a retry burst.
DEFAULT_RATE_LIMIT_PER_MIN = 12

#: One Gemini call should never hold a background task longer than this.
DEFAULT_TIMEOUT_SECONDS = 30.0

#: Retries for one Gemini call, including the first attempt. Three is chosen
#: against the demo, not against a throughput target: two extra tries add at most
#: ~3s of backoff, and a step that stalls longer than that is worse on camera
#: than a step that falls back.
_MAX_ATTEMPTS = 3

#: ``llm_cache.prompt_preview`` is documented as "first 200 chars, for debugging only".
_PREVIEW_CHARS = 200

#: Token-bucket refill and consume, atomically.
#:
#: KEYS[1] is the bucket hash; ARGV is (capacity, refill_per_second, now, cost).
#: Returns 1 if the caller may proceed, 0 if the bucket is empty. The TTL is
#: reset on every call so an idle bucket expires rather than leaking a key per
#: schema name forever.
_TOKEN_BUCKET_LUA = """
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])

local bucket = redis.call('HMGET', KEYS[1], 'tokens', 'updated_at')
local tokens = tonumber(bucket[1])
local updated_at = tonumber(bucket[2])

if tokens == nil then
  tokens = capacity
  updated_at = now
end

local elapsed = math.max(0, now - updated_at)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
end

redis.call('HMSET', KEYS[1], 'tokens', tokens, 'updated_at', now)
redis.call('EXPIRE', KEYS[1], 120)
return allowed
"""


def _is_transient(exc: BaseException) -> bool:
    """Whether a failed Gemini call is worth trying again.

    Timeouts, connection errors and 5xx are the server having a bad moment —
    those retry. A 400 (bad schema) and a 403 (bad key) are ours and will fail
    identically every time, so retrying them only delays the fallback.

    **429 is deliberately not retried.** The free tier's quota does not refill
    inside a backoff window, and hammering it is how a rate-limited demo becomes
    a rate-limited demo with three times the requests. The token bucket in front
    of this is what is supposed to prevent 429 in the first place.
    """
    if isinstance(exc, httpx.TimeoutException | httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def prompt_hash(schema_name: str, prompt: str) -> str:
    """Cache key for one prompt under one schema.

    The schema name is part of the digest, not a separate column, because the
    cache is looked up by a single ``UNIQUE`` constraint on ``prompt_hash``.
    Two schemas fed the same context string must not collide.
    """
    return hashlib.sha256(f"{schema_name}\x00{prompt}".encode()).hexdigest()


class GeminiClient:
    """Cached, rate-limited, fallback-guaranteed access to Gemini.

    Construct via :func:`make_gemini_client` in application code; the explicit
    constructor exists so tests can inject a fake Supabase and no Redis.
    """

    def __init__(
        self,
        supabase_client: Any,
        *,
        api_key: str | None = None,
        redis_url: str | None = None,
        model: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        rate_limit_per_min: int = DEFAULT_RATE_LIMIT_PER_MIN,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._supabase = supabase_client
        # Read at construction so a client built once per request picks up the
        # environment as it is then, but resolved lazily enough that tests can
        # monkeypatch the variable before constructing.
        self._api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        self._redis_url = redis_url
        self._model = model
        self._temperature = temperature
        self._rate_limit_per_min = rate_limit_per_min
        self._timeout_seconds = timeout_seconds

    # ── public API ─────────────────────────────────────────────────────

    async def generate_structured(
        self,
        prompt: str,
        response_schema: dict[str, Any],
        schema_name: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a schema-conforming dict, or ``fallback``. Never raises.

        ``fallback`` is returned unchanged on every failure path, so callers can
        pass the value they would have produced without an LLM and treat the
        result as "the best answer available" rather than branching on success.
        """
        log = logger.bind(schema=schema_name, model=self._model)

        if not self._api_key:
            log.warning("gemini_no_api_key", reason="GEMINI_API_KEY unset — using fallback")
            return fallback

        digest = prompt_hash(schema_name, prompt)

        cached = self._read_cache(digest)
        if cached is not None:
            log.info("gemini_cache_hit", prompt_hash=digest[:12])
            self._bump_hit_count(digest)
            return cached

        if not await self._acquire_token(schema_name):
            log.warning("gemini_rate_limited", reason="token bucket empty — using fallback")
            return fallback

        started = time.monotonic()
        try:
            payload, usage = await self._call_gemini(prompt, response_schema)
        except Exception as exc:  # noqa: BLE001 - the fallback is the error path
            log.warning("gemini_call_failed", error=str(exc))
            return fallback

        missing = _missing_required(payload, response_schema)
        if missing:
            log.warning("gemini_schema_violation", missing=missing)
            return fallback

        latency_ms = int((time.monotonic() - started) * 1000)
        self._write_cache(digest, prompt, payload, usage, latency_ms)
        log.info("gemini_call_complete", prompt_hash=digest[:12], latency_ms=latency_ms)
        return payload

    # ── cache ──────────────────────────────────────────────────────────

    def _read_cache(self, digest: str) -> dict[str, Any] | None:
        """Return the cached response for ``digest``, or ``None``.

        A cache read that fails is a cache miss, not an error: the call is still
        makeable, and refusing to make it because a *cache* is down would be the
        wrong direction to fail in.
        """
        try:
            resp = (
                self._supabase.table("llm_cache")
                .select("response")
                .eq("prompt_hash", digest)
                .limit(1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_cache_read_error", error=str(exc))
            return None

        if not resp.data:
            return None
        response = resp.data[0].get("response")
        # A JSONB column round-trips as a dict, but a cache written by an older
        # client (or a fake that stores text) may hand back a string.
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                return None
        return dict(response) if isinstance(response, dict) else None

    def _bump_hit_count(self, digest: str) -> None:
        """Increment ``hit_count`` for a served cache entry.

        Read-then-write rather than an atomic ``UPDATE ... SET x = x + 1``,
        because PostgREST has no expression update. The counter is
        demo telemetry — "these 9 calls cost nothing" — so a lost increment
        under concurrency is not worth an RPC to fix.
        """
        try:
            current = (
                self._supabase.table("llm_cache")
                .select("hit_count")
                .eq("prompt_hash", digest)
                .limit(1)
                .execute()
            )
            hits = int((current.data[0].get("hit_count") or 0) if current.data else 0)
            self._supabase.table("llm_cache").update({"hit_count": hits + 1}).eq(
                "prompt_hash", digest
            ).execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_cache_hit_count_error", error=str(exc))

    def _write_cache(
        self,
        digest: str,
        prompt: str,
        payload: dict[str, Any],
        usage: dict[str, Any],
        latency_ms: int,
    ) -> None:
        """Store a fresh response. A failed write costs a cache entry, nothing more."""
        row = {
            "prompt_hash": digest,
            "prompt_preview": prompt[:_PREVIEW_CHARS],
            "model": self._model,
            "response": payload,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "latency_ms": latency_ms,
            "hit_count": 0,
        }
        try:
            # Upsert on the UNIQUE prompt_hash: two warm-up runs racing on the
            # same target should converge, not raise a duplicate-key error.
            self._supabase.table("llm_cache").upsert(row, on_conflict="prompt_hash").execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_cache_write_error", error=str(exc))

    # ── rate limiter ───────────────────────────────────────────────────

    async def _acquire_token(self, schema_name: str) -> bool:
        """Take one token from the bucket. Returns ``True`` when Redis is absent.

        Failing open is deliberate — see the module docstring. The bucket is
        keyed per schema name so a burst of listen classifications cannot starve
        the diagnose call on the same case.
        """
        if not self._redis_url:
            return True

        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(self._redis_url)
            try:
                allowed = await client.eval(
                    _TOKEN_BUCKET_LUA,
                    1,
                    f"llm:ratelimit:{schema_name}",
                    self._rate_limit_per_min,
                    self._rate_limit_per_min / 60.0,
                    time.time(),
                    1,
                )
            finally:
                await client.aclose()
            return bool(int(allowed))
        except Exception as exc:  # noqa: BLE001 - a dead limiter must not block the call
            logger.warning("llm_rate_limiter_unavailable", error=str(exc))
            return True

    # ── the call itself ────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception(_is_transient),
        # Re-raise the underlying error rather than tenacity's RetryError, so the
        # warning `generate_structured` logs names the actual failure.
        reraise=True,
    )
    async def _call_gemini(
        self,
        prompt: str,
        response_schema: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """POST to ``generateContent`` and parse the JSON body out of the candidate.

        Retries transient server-side failures; see :func:`_is_transient`. Raises
        on anything else, and ``generate_structured`` — the only caller — turns
        every exception into the fallback.
        """
        url = f"{GEMINI_API_BASE}/{self._model}:generateContent"
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self._temperature,
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            },
        }

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            resp = await client.post(
                url,
                json=body,
                # Header rather than `?key=`, so the key never lands in a proxy
                # access log or an httpx exception's request URL.
                headers={"x-goog-api-key": self._api_key or ""},
            )
            resp.raise_for_status()
            data = resp.json()

        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError(f"Gemini returned a {type(parsed).__name__}, expected an object")

        meta = data.get("usageMetadata") or {}
        usage = {
            "input_tokens": meta.get("promptTokenCount"),
            "output_tokens": meta.get("candidatesTokenCount"),
        }
        return parsed, usage


def _missing_required(payload: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Top-level required keys the payload does not carry.

    Only the top level is checked. Nested objects in these schemas are either
    optional or fully nullable, and a deep validator would reject responses the
    callers handle fine — a stricter check that costs recoveries is not a
    stricter check worth having.
    """
    required = schema.get("required") or []
    return [key for key in required if key not in payload]


def make_gemini_client(supabase_client: Any) -> GeminiClient:
    """Build a client from the environment.

    ``REDIS_URL`` is optional: without it the rate limiter is skipped entirely
    rather than degraded, which is the right shape for local development and for
    the tests, neither of which run a Redis.
    """
    return GeminiClient(
        supabase_client,
        api_key=os.environ.get("GEMINI_API_KEY"),
        redis_url=os.environ.get("REDIS_URL"),
    )
