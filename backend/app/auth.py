"""Verification of Supabase-issued JWTs.

We do not mint tokens ourselves anywhere in this codebase — the only job here is
to prove that a token the browser presented really came from Supabase Auth and
has not expired.

**How Supabase signs.** Two schemes coexist, and a project moves from the first
to the second:

*Legacy.* One symmetric secret per project (``SUPABASE_JWT_SECRET``), HS256.
Verifying means holding a copy of the signing secret — every service that
validates a token could also forge one.

*Signing keys.* An asymmetric key pair, ES256 (or RS256), whose **public** half
is published at ``/auth/v1/.well-known/jwks.json``. Verifiers hold nothing
secret, and keys can be rotated without redeploying anything.

This module handles both, because a project mid-migration issues one and still
honours the other, and because which one is active is a dashboard setting rather
than something this repo can pin. Assuming HS256 is how a perfectly valid
session gets a 401 from the API while the frontend's own ``getUser()`` succeeds:
the session was never the problem, the verifier was.

**On trusting the header's ``alg``.** Taking the algorithm from the token is the
setup for an algorithm-confusion downgrade: re-sign an ES256 token as HS256
using the published public key — which is not a secret — as the HMAC key. The
defence below is structural rather than a check. The key *material* is selected
by algorithm class: an asymmetric ``alg`` can only ever reach a JWKS public key,
and HS256 can only ever reach the configured secret. There is no path by which a
public key becomes an HMAC secret, and anything outside the allow-list is
rejected before a key is looked up at all.
"""

import threading
import time
from typing import Any

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import get_settings
from app.logging import get_logger

logger = get_logger(__name__)

#: The legacy per-project shared secret.
_SYMMETRIC_ALGORITHMS = frozenset({"HS256"})

#: Signing keys. ES256 is what Supabase creates by default; RS256 is offered too.
_ASYMMETRIC_ALGORITHMS = frozenset({"ES256", "RS256"})

#: Supabase sets ``aud`` to "authenticated" for a signed-in user.
_AUDIENCE = "authenticated"

#: How long a fetched key set is trusted before being refreshed. Supabase's own
#: guidance is to cache; keys change on rotation, which is rare and deliberate.
_JWKS_TTL_SECONDS = 600

#: Floor between refetches triggered by an unrecognised ``kid``. Without it a
#: stream of tokens carrying a bogus kid becomes a stream of requests to the
#: auth server — an unauthenticated caller should not be able to generate load
#: on a third party through us.
_JWKS_MIN_REFETCH_SECONDS = 30


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _fetch_jwks() -> list[dict[str, Any]]:
    """Return the project's currently published signing keys.

    Patched in tests, which is also what keeps the suite off the network.
    """
    url = f"{get_settings().SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
    response = httpx.get(url, timeout=5.0)
    response.raise_for_status()
    keys = response.json().get("keys", [])
    return [key for key in keys if isinstance(key, dict) and key.get("kid")]


class _JwksCache:
    """The published key set, cached with a TTL and refreshed on a cache miss.

    Locked because FastAPI runs sync dependencies in a thread pool, so several
    requests can land here at once. The lock is held across the fetch on
    purpose: the alternative is every concurrent request on a cold cache making
    its own HTTP call to discover the same key.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at = 0.0

    def get(self, kid: str) -> dict[str, Any] | None:
        """Return the JWK for ``kid``, refetching if it is unknown or stale."""
        with self._lock:
            now = time.monotonic()
            stale = now - self._fetched_at >= _JWKS_TTL_SECONDS
            # A kid we have never seen is the signal that a rotation happened
            # inside the TTL, so treat it as a reason to refresh early — rate
            # limited, so an unknown kid cannot be replayed as a fetch loop.
            missing = kid not in self._keys and now - self._fetched_at >= _JWKS_MIN_REFETCH_SECONDS

            if stale or missing or not self._fetched_at:
                self._refresh(now)

            return self._keys.get(kid)

    def _refresh(self, now: float) -> None:
        """Replace the cached keys. Called with the lock held."""
        try:
            keys = _fetch_jwks()
        except (httpx.HTTPError, ValueError) as exc:
            # Keep serving the keys we already have. A transient blip at
            # Supabase should not log everybody out; only report it.
            logger.warning("jwt.jwks_fetch_failed", error=str(exc))
            # Still stamp the attempt, so a hard outage does not turn into a
            # retry on every single request.
            self._fetched_at = now
            return

        self._keys = {key["kid"]: key for key in keys}
        self._fetched_at = now

    def reset(self) -> None:
        with self._lock:
            self._keys = {}
            self._fetched_at = 0.0


_jwks_cache = _JwksCache()


def reset_jwks_cache() -> None:
    """Drop the cached key set. For tests, and after a deliberate rotation."""
    _jwks_cache.reset()


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """Decode and validate a Supabase access token.

    Args:
        token: The raw JWT, without the ``Bearer `` prefix.

    Returns:
        The decoded claims. ``sub`` is the Supabase user id, which is also the
        merchant id throughout this schema.

    Raises:
        HTTPException: 401 if the signature, expiry, or required claims fail.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise _unauthorized("Invalid or expired token") from exc

    algorithm = header.get("alg")
    kid = header.get("kid")

    key: Any
    if algorithm in _ASYMMETRIC_ALGORITHMS:
        key = _jwks_cache.get(kid) if kid else None
        if key is None:
            # Almost always a rotation this process has not caught up with, or a
            # token from a different project. Logged with the kid because that
            # is the one field that tells the two apart.
            logger.warning("jwt.unknown_signing_key", alg=algorithm, kid=kid)
            raise _unauthorized("Invalid or expired token")
    elif algorithm in _SYMMETRIC_ALGORITHMS:
        key = get_settings().SUPABASE_JWT_SECRET
        if not key:
            logger.warning("jwt.no_symmetric_secret_configured", alg=algorithm)
            raise _unauthorized("Invalid or expired token")
    else:
        # Includes "none", and anything else a forger might put here.
        logger.warning("jwt.unsupported_algorithm", alg=algorithm, kid=kid)
        raise _unauthorized("Invalid or expired token")

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            key,
            # Single-element list, pinned to the branch taken above. Passing the
            # whole allow-list here would hand the choice of key back to the
            # token, which is the confusion this structure exists to prevent.
            algorithms=[algorithm],
            audience=_AUDIENCE,
        )
    except JWTError as exc:
        # The reason (bad signature vs. expired vs. wrong audience) never
        # reaches the client — a 401 should not be an oracle — but without it in
        # the log a misconfiguration is indistinguishable from an expired tab.
        logger.warning("jwt.rejected", alg=algorithm, kid=kid, reason=str(exc))
        raise _unauthorized("Invalid or expired token") from exc

    if not payload.get("sub"):
        raise _unauthorized("Token is missing a subject claim")

    return payload
