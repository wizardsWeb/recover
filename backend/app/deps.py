"""FastAPI dependencies shared across routers."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client

from app.auth import verify_supabase_jwt
from app.db import get_user_client

# auto_error=False so a missing header produces our own 401 with a consistent
# JSON body, rather than FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False)


def get_access_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Extract the bearer token, or raise 401."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def get_current_user_id(
    token: Annotated[str, Depends(get_access_token)],
) -> str:
    """Return the Supabase user id (= merchant id) for the current request."""
    payload = verify_supabase_jwt(token)
    return str(payload["sub"])


def get_user_supabase(
    token: Annotated[str, Depends(get_access_token)],
) -> Client:
    """Return a Supabase client that runs queries under the caller's RLS policies."""
    return get_user_client(token)


CurrentUserId = Annotated[str, Depends(get_current_user_id)]
UserSupabase = Annotated[Client, Depends(get_user_supabase)]
