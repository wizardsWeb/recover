"""Signature verification for Supabase access tokens.

The project this app talks to has migrated to asymmetric JWT *signing keys*, so
the tokens the browser presents are signed ES256 against a key published in the
project's JWKS — not HS256 against the legacy shared secret. Both have to work:
Supabase keeps the legacy key valid alongside the new one while a project
migrates, so a verifier that handles only one of them rejects real users.

Nothing here touches the network. `_fetch_jwks` is patched, which is also what
proves the fetch is cached rather than made per request.
"""

import time
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from jose import jwt

from app import auth

KID = "640c7f5e-3010-4526-b42e-5564800f984a"
MERCHANT_ID = "11111111-1111-1111-1111-111111111111"


def _es256_keypair(kid: str = KID) -> tuple[str, dict[str, Any]]:
    """Return a PEM private key and the public JWK a JWKS would publish for it."""
    private = ec.generate_private_key(ec.SECP256R1())
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    numbers = private.public_key().public_numbers()

    def b64(value: int) -> str:
        import base64

        return base64.urlsafe_b64encode(value.to_bytes(32, "big")).decode().rstrip("=")

    return pem, {
        "kty": "EC",
        "crv": "P-256",
        "alg": "ES256",
        "use": "sig",
        "key_ops": ["verify"],
        "kid": kid,
        "x": b64(numbers.x),
        "y": b64(numbers.y),
    }


def _claims(**overrides: Any) -> dict[str, Any]:
    """The claim set Supabase Auth puts in an access token."""
    now = int(time.time())
    claims = {
        "sub": MERCHANT_ID,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return claims


@pytest.fixture(autouse=True)
def _clear_jwks_cache() -> None:
    """Keys cached by one test must not be visible to the next."""
    auth.reset_jwks_cache()


def test_es256_token_signed_by_a_published_key_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pem, public_jwk = _es256_keypair()
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: [public_jwk])

    token = jwt.encode(_claims(), pem, algorithm="ES256", headers={"kid": KID})

    assert auth.verify_supabase_jwt(token)["sub"] == MERCHANT_ID


def test_legacy_hs256_token_is_still_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """A project mid-migration still has users holding HS256 tokens."""
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: [])

    token = jwt.encode(_claims(), "test-jwt-secret", algorithm="HS256")

    assert auth.verify_supabase_jwt(token)["sub"] == MERCHANT_ID


def test_es256_token_from_an_unpublished_key_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    """Right kid, wrong key: the signature must not verify."""
    attacker_pem, _ = _es256_keypair()
    _, published_jwk = _es256_keypair()
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: [published_jwk])

    token = jwt.encode(_claims(), attacker_pem, algorithm="ES256", headers={"kid": KID})

    with pytest.raises(HTTPException) as raised:
        auth.verify_supabase_jwt(token)
    assert raised.value.status_code == 401


def test_es256_token_with_an_unknown_kid_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    pem, published_jwk = _es256_keypair(kid="some-other-key")
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: [published_jwk])

    token = jwt.encode(_claims(), pem, algorithm="ES256", headers={"kid": KID})

    with pytest.raises(HTTPException) as raised:
        auth.verify_supabase_jwt(token)
    assert raised.value.status_code == 401


def test_expired_es256_token_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    pem, public_jwk = _es256_keypair()
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: [public_jwk])

    now = int(time.time())
    token = jwt.encode(
        _claims(iat=now - 7200, exp=now - 3600), pem, algorithm="ES256", headers={"kid": KID}
    )

    with pytest.raises(HTTPException) as raised:
        auth.verify_supabase_jwt(token)
    assert raised.value.status_code == 401


def test_none_algorithm_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The alg comes from the token header, so the allow-list is load-bearing."""
    pem, public_jwk = _es256_keypair()
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: [public_jwk])

    import base64
    import json

    def segment(value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip("=")

    unsigned = f"{segment({'alg': 'none', 'typ': 'JWT'})}.{segment(_claims())}."

    with pytest.raises(HTTPException) as raised:
        auth.verify_supabase_jwt(unsigned)
    assert raised.value.status_code == 401


def test_public_key_cannot_be_used_as_an_hmac_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The classic algorithm-confusion downgrade must not work.

    An attacker who re-signs the claims as HS256 using the *published public
    key* as the shared secret succeeds against any verifier that picks its key
    by kid and its algorithm by header. Here the key material is chosen by
    algorithm class, so a JWKS key is never reachable as an HMAC secret.
    """
    _, public_jwk = _es256_keypair()
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: [public_jwk])

    forged = jwt.encode(_claims(), public_jwk["x"], algorithm="HS256", headers={"kid": KID})

    with pytest.raises(HTTPException) as raised:
        auth.verify_supabase_jwt(forged)
    assert raised.value.status_code == 401


def test_wrong_audience_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    pem, public_jwk = _es256_keypair()
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: [public_jwk])

    token = jwt.encode(_claims(aud="anon"), pem, algorithm="ES256", headers={"kid": KID})

    with pytest.raises(HTTPException) as raised:
        auth.verify_supabase_jwt(token)
    assert raised.value.status_code == 401


def test_jwks_is_fetched_once_across_many_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """One HTTP round trip per TTL, not one per request."""
    pem, public_jwk = _es256_keypair()
    calls = 0

    def counting_fetch() -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return [public_jwk]

    monkeypatch.setattr(auth, "_fetch_jwks", counting_fetch)

    for _ in range(5):
        token = jwt.encode(_claims(), pem, algorithm="ES256", headers={"kid": KID})
        auth.verify_supabase_jwt(token)

    assert calls == 1


def test_a_rotated_key_is_picked_up_without_a_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    """A kid the cache has never seen means the project rotated inside the TTL."""
    old_pem, old_jwk = _es256_keypair(kid="old-key")
    new_pem, new_jwk = _es256_keypair(kid="new-key")
    published = [old_jwk]
    calls = 0

    def counting_fetch() -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return published

    monkeypatch.setattr(auth, "_fetch_jwks", counting_fetch)
    # The floor exists to stop a bogus kid becoming a fetch loop; a rotation
    # arriving seconds after the last fetch is the case it must not block, so
    # the test measures the refetch itself rather than waiting out the clock.
    monkeypatch.setattr(auth, "_JWKS_MIN_REFETCH_SECONDS", 0)

    old_token = jwt.encode(_claims(), old_pem, algorithm="ES256", headers={"kid": "old-key"})
    assert auth.verify_supabase_jwt(old_token)["sub"] == MERCHANT_ID
    assert calls == 1

    published = [old_jwk, new_jwk]
    new_token = jwt.encode(_claims(), new_pem, algorithm="ES256", headers={"kid": "new-key"})

    assert auth.verify_supabase_jwt(new_token)["sub"] == MERCHANT_ID
    assert calls == 2


def test_an_unknown_kid_does_not_refetch_on_every_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otherwise an unauthenticated caller can drive load onto Supabase through us."""
    pem, public_jwk = _es256_keypair()
    calls = 0

    def counting_fetch() -> list[dict[str, Any]]:
        nonlocal calls
        calls += 1
        return [public_jwk]

    monkeypatch.setattr(auth, "_fetch_jwks", counting_fetch)

    # Warm the cache, so the misses below are misses rather than a cold start.
    auth.verify_supabase_jwt(jwt.encode(_claims(), pem, algorithm="ES256", headers={"kid": KID}))
    assert calls == 1

    unknown = jwt.encode(_claims(), pem, algorithm="ES256", headers={"kid": "nope"})
    for _ in range(5):
        with pytest.raises(HTTPException):
            auth.verify_supabase_jwt(unknown)

    assert calls == 1


def test_malformed_token_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: [])

    with pytest.raises(HTTPException) as raised:
        auth.verify_supabase_jwt("not-a-real-jwt")
    assert raised.value.status_code == 401


def test_token_without_a_subject_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    pem, public_jwk = _es256_keypair()
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: [public_jwk])

    claims = _claims()
    del claims["sub"]
    token = jwt.encode(claims, pem, algorithm="ES256", headers={"kid": KID})

    with pytest.raises(HTTPException) as raised:
        auth.verify_supabase_jwt(token)
    assert raised.value.status_code == 401
