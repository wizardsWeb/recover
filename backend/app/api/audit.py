"""The audit trail, read-only.

There is no write endpoint here on purpose. Audit rows are written by the agent
as a side effect of doing the thing they describe; an API that could append to
the trail independently would make the trail evidence of nothing.
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Query

from app.deps import CurrentUserId, UserSupabase

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], result.data or [])


@router.get("")
async def list_audit_events(
    user_id: CurrentUserId,
    supabase: UserSupabase,
    case_id: Annotated[str | None, Query()] = None,
    actor: Annotated[str | None, Query()] = None,
    event_prefix: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Return audit events for the current merchant, newest first.

    ``event_prefix`` matches the ``<step>:<label>`` convention the agent writes,
    so ``guardrail`` returns every guardrail verdict across every case.
    """
    query = (
        supabase.table("audit_events")
        .select("*")
        .eq("merchant_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if case_id:
        query = query.eq("case_id", case_id)
    if actor:
        query = query.eq("actor", actor)
    if event_prefix:
        query = query.like("event", f"{event_prefix}%")

    return {"audit_events": _rows(query.execute()), "offset": offset, "limit": limit}
