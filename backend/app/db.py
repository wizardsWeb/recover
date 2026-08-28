"""Supabase client construction.

Two very different clients live here, and the distinction matters:

``service_client``
    Authenticates with the service-role key, which **bypasses RLS**. Use it only
    for work that is legitimately cross-tenant (network statistics, the bandit
    arm catalogue, background jobs). Never hand it a merchant id that came from
    a request body.

``get_user_client(jwt)``
    Authenticates as the signed-in user by attaching their access token, so
    every query runs under the RLS policies in the initial migration. This is
    the default for anything serving a request — tenant isolation is then
    enforced by Postgres rather than by us remembering a WHERE clause.

``get_redis_client()``
    Pub/sub for network alerts. Not a database — nothing is stored in it that
    is not already a row in Postgres first.
"""

from functools import lru_cache

import redis.asyncio as redis
from redis.asyncio import Redis
from supabase import Client, create_client

from app.config import get_settings


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    """Return the shared service-role client. Bypasses RLS — use deliberately."""
    settings = get_settings()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


def get_user_client(access_token: str) -> Client:
    """Return a client scoped to one user's access token.

    The client is built per request rather than cached: the token is
    per-request state, and caching by token would keep expired sessions alive.
    """
    settings = get_settings()
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
    # Attaches `Authorization: Bearer <token>` to PostgREST calls, so RLS sees
    # the real auth.uid() instead of the anonymous role.
    client.postgrest.auth(access_token)
    return client


@lru_cache(maxsize=1)
def get_redis_client() -> "Redis":
    """Return the shared Redis client used for network alert fan-out.

    With no ``REDIS_URL`` this hands back an in-process ``fakeredis`` instead of
    failing. That is a development affordance, not a fallback worth relying on:
    a fake is per-process, so pub/sub reaches only subscribers inside the same
    worker. One uvicorn process on a laptop is exactly that, and a deployment
    with more than one is exactly not — which is why production sets the URL and
    the startup log says which of the two is in use.

    Nothing here is on the recovery path. Redis carries dashboard notifications;
    the alert row in Postgres is what actually blocks a retry, and it is written
    before anything is published.
    """
    url = get_settings().REDIS_URL.strip()
    if url:
        return redis.from_url(url, encoding="utf-8", decode_responses=True)

    import fakeredis.aioredis

    return fakeredis.aioredis.FakeRedis(decode_responses=True)
