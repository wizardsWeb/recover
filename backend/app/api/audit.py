"""The audit trail, read-only.

There is no write endpoint here on purpose. Audit rows are written by the agent
as a side effect of doing the thing they describe; an API that could append to
the trail independently would make the trail evidence of nothing.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, HTTPException, Query, status

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
    since: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Return audit events for the current merchant, newest first.

    ``event_prefix`` matches the ``<step>:<label>`` convention the agent writes,
    so ``guardrail`` returns every guardrail verdict across every case.

    ``since`` is an ISO timestamp, and exists so a link can scope the log to a
    window someone is asking about — the batch results screen points here with
    the run's start time. Compared as a string, which sorts correctly only
    because every timestamp the database returns is UTC at the same precision;
    an offset-bearing value from a client would compare wrongly, so it is
    normalised before use.
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
    if since:
        query = query.gte("created_at", _as_utc(since))

    return {"audit_events": _rows(query.execute()), "offset": offset, "limit": limit}


def _as_utc(stamp: str) -> str:
    """Normalise a caller-supplied timestamp to UTC, or 400.

    An unparseable value is rejected rather than ignored: silently dropping the
    filter would return the whole log under a heading saying it was scoped.
    """
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"`since` must be an ISO timestamp, got {stamp!r}.",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()
