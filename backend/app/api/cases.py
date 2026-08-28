"""Recovery case read endpoints and the human override.

Every query here goes through the caller's Supabase client, so RLS scopes each
one to the signed-in merchant. The explicit ``eq("merchant_id", ...)`` filters
are belt-and-braces: they make the intent readable and they keep the query
correct if it is ever moved to a service-role context.

Responses are the raw row shape — snake_case, straight from PostgREST — because
the case payload is a deep tree (audit events, decisions, attempts, replies) and
re-modelling it in camelCase would mean maintaining a second copy of the schema
for no gain. ``lib/api/cases.ts`` on the frontend types it in the same casing.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.agent.handoff import create_handoff_attempt
from app.deps import CurrentUserId, UserSupabase
from app.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/cases", tags=["cases"])

#: The columns the list view needs. Selecting explicitly keeps the diagnosis
#: blob — which can be large once Phase 5 lands — out of a 100-row response.
_LIST_COLUMNS = (
    "id, status, playbook, amount_at_risk_cents, amount_recovered_cents, "
    "opened_at, closed_at, current_step, uplift_bucket, "
    "customers(name, email)"
)

_OVERRIDE_ACTIONS = {"pause": "stopped", "stop": "stopped", "escalate": "in_flight"}


class HandoffRequest(BaseModel):
    """A human taking a case out of the agent's hands, with a note for whoever picks it up."""

    reason: Annotated[str, Field(max_length=1000)] = "Escalated from the case detail page"


class OverrideRequest(BaseModel):
    """A human taking a case away from the agent."""

    action: Annotated[str, Field(pattern="^(pause|stop|escalate)$")]
    reason: Annotated[str, Field(max_length=1000)] = "Manual override"


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], result.data or [])


@router.get("")
async def list_cases(
    user_id: CurrentUserId,
    supabase: UserSupabase,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    playbook: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """Return a paginated list of cases for the current merchant, newest first."""
    query = (
        supabase.table("recovery_cases")
        .select(_LIST_COLUMNS)
        .eq("merchant_id", user_id)
        .order("opened_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if status_filter:
        query = query.eq("status", status_filter)
    if playbook:
        query = query.eq("playbook", playbook)

    return {"cases": _rows(query.execute()), "offset": offset, "limit": limit}


@router.get("/{case_id}")
async def get_case(
    case_id: str,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> dict[str, Any]:
    """Return one case with its full trail.

    The four related collections are fetched separately rather than as one
    embedded select: they are independent lists with their own orderings, and a
    single nested query would make the ordering of each implicit.
    """
    case_resp = (
        supabase.table("recovery_cases")
        .select("*, customers(*)")
        .eq("id", case_id)
        .eq("merchant_id", user_id)
        .limit(1)
        .execute()
    )
    if not case_resp.data:
        # RLS already hides other merchants' cases, so "not found" and "not
        # yours" are the same answer — and 404 is the right one for both.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    case = _rows(case_resp)[0]

    def related(table: str, order_column: str) -> list[dict[str, Any]]:
        """Oldest first — these render as a timeline, which reads forwards."""
        return _rows(
            supabase.table(table)
            .select("*")
            .eq("case_id", case_id)
            .order(order_column, desc=False)
            .execute()
        )

    return {
        **case,
        "audit_events": related("audit_events", "created_at"),
        "agent_decisions": related("agent_decisions", "step_number"),
        "execution_attempts": related("execution_attempts", "attempted_at"),
        "customer_replies": related("customer_replies", "received_at"),
    }


@router.post("/{case_id}/override")
async def override_case(
    case_id: str,
    payload: OverrideRequest,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> dict[str, Any]:
    """Human override: pause, stop, or escalate a case.

    The audit row is the point. An agent that can be overridden without a record
    is an agent nobody can be held accountable for — in either direction.
    """
    new_status = _OVERRIDE_ACTIONS[payload.action]

    owned = (
        supabase.table("recovery_cases")
        .select("id")
        .eq("id", case_id)
        .eq("merchant_id", user_id)
        .limit(1)
        .execute()
    )
    if not owned.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    now = datetime.now(UTC).isoformat()
    supabase.table("recovery_cases").update(
        {
            "status": new_status,
            "current_step": f"human_{payload.action}",
            "updated_at": now,
        }
    ).eq("id", case_id).execute()

    supabase.table("audit_events").insert(
        {
            "case_id": case_id,
            "merchant_id": user_id,
            "actor": "human",
            "event": f"human_override:{payload.action}",
            "details": {"reason": payload.reason, "new_status": new_status},
            "created_at": now,
            "updated_at": now,
        }
    ).execute()

    return {"case_id": case_id, "action": payload.action, "new_status": new_status}


@router.post("/{case_id}/handoff")
async def create_handoff(
    case_id: str,
    payload: HandoffRequest,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> dict[str, Any]:
    """Write a handoff briefing for a case a human is taking over.

    Separate from ``/override`` on purpose. The override changes what the *agent*
    does; this produces what the *person* reads. An escalation needs both, and a
    merchant who escalates without a briefing has moved the case to a queue where
    nobody knows why it is there.

    Deliberately assembled from case data with no model in the loop — see
    ``app.agent.handoff``. The card is acted on hours later and at face value.
    """
    case_resp = (
        supabase.table("recovery_cases")
        .select("*, customers(*)")
        .eq("id", case_id)
        .eq("merchant_id", user_id)
        .limit(1)
        .execute()
    )
    if not case_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    case = _rows(case_resp)[0]
    customer = case.get("customers") if isinstance(case.get("customers"), dict) else None

    # The trace id ties this row to the audit entry the override wrote, so the
    # two halves of one human action can be read back together.
    trace_id = uuid.uuid4().hex
    handoff = create_handoff_attempt(
        supabase,
        case,
        customer,
        "human_escalation",
        merchant_id=user_id,
        trace_id=trace_id,
        note=payload.reason,
    )
    if handoff is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create the handoff",
        )

    log.info("case_handoff_created", case_id=case_id, merchant_id=user_id, trace_id=trace_id)
    return {"case_id": case_id, "handoff": handoff, "trace_id": trace_id}
