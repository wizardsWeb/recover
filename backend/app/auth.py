"""Verification of Supabase-issued JWTs.

Supabase signs access tokens with the project's JWT secret using HS256. We do
not mint tokens ourselves anywhere in this codebase — the only job here is to
prove that a token the browser presented really came from Supabase and has not
expired.
"""

from typing import Any

from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import get_settings

ALGORITHM = "HS256"


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
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=[ALGORITHM],
            # Supabase sets aud to "authenticated" for signed-in users.
            audience="authenticated",
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing a subject claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
