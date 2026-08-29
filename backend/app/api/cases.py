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

from app.agent.causal_dag import traverse_dag
from app.agent.causal_dag.definitions import DAG_VERSION, get_dag
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
    include_synthetic: Annotated[bool, Query(alias="includeSynthetic")] = False,
) -> dict[str, Any]:
    """Return a paginated list of cases for the current merchant, newest first.

    Batch-simulated cases are hidden unless asked for. A thousand-case run would
    otherwise bury every real case below a page of manufactured ones, and the
    list is where a merchant goes to look at work the agent actually did.
    """
    query = (
        supabase.table("recovery_cases")
        .select(_LIST_COLUMNS)
        .eq("merchant_id", user_id)
        .order("opened_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    if not include_synthetic:
        query = query.is_("metadata->>is_batch_synthetic", "null")
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


@router.get("/{case_id}/dag")
async def get_case_dag(
    case_id: str,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> dict[str, Any]:
    """The causal graph for this case's playbook, and the path taken through it.

    Structure and traversal in one response. They are always rendered together —
    a diagram with no highlighted path explains nothing, and a path with no
    diagram to lay it over is a list of node ids — and splitting them would mean
    two round trips whose answers can disagree about which DAG version they came
    from.

    Nodes and edges come from `definitions.py` rather than from the `causal_dag`
    table, even though the seeder keeps that table current. The Python
    definitions are what the traversal actually ran against, so serving anything
    else could show a merchant a graph that does not explain their own case —
    the seeded rows exist for inspection and for future work that would learn
    from them, not as the source the UI reads.
    """
    case_resp = (
        supabase.table("recovery_cases")
        .select("id, playbook, diagnosis")
        .eq("id", case_id)
        .eq("merchant_id", user_id)
        .limit(1)
        .execute()
    )
    if not case_resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    case = _rows(case_resp)[0]

    playbook = str(case.get("playbook") or "")
    dag = get_dag(playbook)
    if dag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No causal graph for playbook {playbook!r}.",
        )

    raw_diagnosis = case.get("diagnosis")
    diagnosis: dict[str, Any] = raw_diagnosis if isinstance(raw_diagnosis, dict) else {}
    raw_observed = diagnosis.get("observed_features")
    observed: dict[str, bool] = raw_observed if isinstance(raw_observed, dict) else {}

    # Re-run the traversal rather than reading the stored posteriors. The
    # diagnosis row keeps the winner and its probability but not the full
    # distribution, and the sidebar charts all of them. Recomputing from the
    # stored features is deterministic, so it cannot disagree with what the
    # agent concluded — and if it ever did, that would mean the graph changed
    # under a closed case, which `dag_version` is there to make visible.
    traversal = traverse_dag(playbook, observed) if observed else None

    return {
        "playbook": playbook,
        "dag_version": DAG_VERSION,
        "nodes": [
            {
                "node_id": node.node_id,
                "node_type": node.node_type,
                "label": node.label,
                "description": node.description,
                "prior_probability": node.prior_probability,
                "base_rate": node.base_rate,
            }
            for node in dag.nodes
        ],
        "edges": [
            {"from": edge.from_node, "to": edge.to_node, "likelihood": edge.likelihood}
            for edge in dag.edges
        ],
        # Null for a case diagnosed before Phase 12, or by the model-led
        # fallback. The tab is hidden in that state rather than rendering an
        # unexplained graph with nothing lit up.
        "traversal": (
            {
                "observed_features": observed,
                "posteriors": traversal["posteriors"],
                "causal_path": traversal["causal_path"],
                "root_cause": traversal["root_cause"],
                "posterior_probability": traversal["posterior_probability"],
                "alternative_hypotheses": traversal["alternative_hypotheses"],
            }
            if traversal
            else None
        ),
    }
