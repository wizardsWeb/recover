"""Merchant profile endpoints.

Every query here goes through the user-scoped Supabase client, so RLS — not
application code — is what guarantees a merchant can only touch their own row.
The `eq("id", user_id)` filters are for selecting the right row, not for
security.
"""

from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.deps import CurrentUserId, UserSupabase
from app.logging import get_logger

router = APIRouter(prefix="/api/merchants", tags=["merchants"])
log = get_logger(__name__)

Vertical = Literal["d2c_beauty", "edtech_subscription", "b2b_distribution", "other"]


class CamelModel(BaseModel):
    """Base model that speaks camelCase on the wire and snake_case in Python."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class Merchant(CamelModel):
    id: str
    name: str
    vertical: Vertical | None = None
    onboarded: bool
    playbook_config: dict[str, Any] = Field(default_factory=dict)
    timezone: str
    created_at: str
    updated_at: str


class MerchantUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    vertical: Vertical | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class MerchantOnboard(CamelModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    vertical: Vertical


def _as_row(record: object) -> dict[str, Any]:
    """Narrow one PostgREST result row to a plain dict.

    supabase-py types `.data` as a broad JSON union, so the cast is where we
    state the shape we already know a `merchants` row has.
    """
    return cast(dict[str, Any], record)


def _fetch_merchant(supabase: Any, user_id: str) -> dict[str, Any]:
    """Read the caller's merchant row, or raise 404."""
    result = supabase.table("merchants").select("*").eq("id", user_id).limit(1).execute()
    if not result.data:
        # The signup trigger should have created this row. If it is missing the
        # account is in a broken state and silently creating one here would hide
        # a real problem.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No merchant record for this account",
        )
    return _as_row(result.data[0])


@router.get("/me", response_model=Merchant)
def get_me(user_id: CurrentUserId, supabase: UserSupabase) -> Merchant:
    """Return the signed-in merchant's profile."""
    return Merchant.model_validate(_fetch_merchant(supabase, user_id))


@router.patch("/me", response_model=Merchant)
def update_me(
    payload: MerchantUpdate,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> Merchant:
    """Update name, vertical, and/or timezone."""
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    result = supabase.table("merchants").update(changes).eq("id", user_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No merchant record for this account",
        )

    log.info("merchant.updated", merchant_id=user_id, fields=sorted(changes))
    return Merchant.model_validate(_as_row(result.data[0]))


@router.post("/onboard", response_model=Merchant)
def onboard(
    payload: MerchantOnboard,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> Merchant:
    """Complete first-run setup. Rejected if the merchant is already onboarded."""
    current = _fetch_merchant(supabase, user_id)
    if current.get("onboarded"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Merchant is already onboarded",
        )

    result = (
        supabase.table("merchants")
        .update({"name": payload.name, "vertical": payload.vertical, "onboarded": True})
        .eq("id", user_id)
        .execute()
    )
    log.info("merchant.onboarded", merchant_id=user_id, vertical=payload.vertical)
    return Merchant.model_validate(_as_row(result.data[0]))
