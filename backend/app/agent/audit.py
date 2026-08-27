"""Step 9 — Audit: the trail that makes the agent defensible.

This is the second module in Phase 4 with no stub in it, for the same reason as
the guardrail: an autonomous agent that spends a merchant's goodwill and touches
a customer's phone has to be able to account for every decision afterwards. The
audit trail is what turns "the AI sent it" into a reconstructable chain —
what was diagnosed, which arms were considered, which rule vetoed what, and what
was actually attempted.

Two conventions hold the trail together:

* **``trace_id`` threads one loop pass.** Every row from a single pass shares
  it, and ``idx_audit_events_trace_id`` exists so the whole pass can be pulled
  back in one query. A UI timeline is then a filter, not a join.
* **``event`` is ``"<step>:<label>"``.** Prefixing with the step name means the
  nine steps sort and group without a separate column, and a new event type in
  Phase 6 cannot collide with one from Phase 4.

The per-step helpers below each pick a deliberate subset of their step's result
rather than dumping the whole model. A diagnosis's full evidence list belongs in
``recovery_cases.diagnosis``; what the trail needs is the claim, the confidence,
and whether a model or a stub produced it.
"""

from datetime import UTC, datetime
from typing import Any

from app.logging import get_logger

logger = get_logger(__name__)


async def log_agent_step(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    step_name: str,
    actor: str,
    event_label: str,
    details: dict[str, Any],
    trace_id: str,
) -> str:
    """Write a single ``audit_events`` row. Returns the audit event id."""
    now = datetime.now(UTC).isoformat()
    row = {
        "case_id": case_id,
        "merchant_id": merchant_id,
        "actor": actor,
        "event": f"{step_name}:{event_label}",
        "details": details,
        "trace_id": trace_id,
        "created_at": now,
        "updated_at": now,
    }
    resp = supabase_client.table("audit_events").insert(row).execute()
    if resp.data:
        return str(resp.data[0]["id"])
    return ""


async def log_case_opened(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    playbook: str,
    amount_at_risk_cents: int,
    trace_id: str,
) -> None:
    """Record that the agent picked up a case and routed it to a playbook."""
    await log_agent_step(
        supabase_client,
        case_id,
        merchant_id,
        "detect",
        "agent",
        "case_opened",
        {"playbook": playbook, "amount_at_risk_cents": amount_at_risk_cents},
        trace_id,
    )


async def log_diagnosis(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    diagnosis: dict[str, Any],
    trace_id: str,
) -> None:
    """Record the root cause and how confident the agent is in it."""
    await log_agent_step(
        supabase_client,
        case_id,
        merchant_id,
        "diagnose",
        "agent",
        "diagnosis_complete",
        {
            "root_cause": diagnosis.get("root_cause"),
            "posterior_probability": diagnosis.get("posterior_probability"),
            "causal_path": diagnosis.get("causal_path"),
            "is_stub": diagnosis.get("is_stub", True),
        },
        trace_id,
    )


async def log_uplift_verdict(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    uplift: dict[str, Any],
    trace_id: str,
) -> None:
    """Record whether contacting this customer was judged worthwhile."""
    await log_agent_step(
        supabase_client,
        case_id,
        merchant_id,
        "uplift_check",
        "agent",
        "uplift_verdict",
        {
            "bucket": uplift.get("bucket"),
            "verdict": uplift.get("verdict"),
            "estimated_lift": uplift.get("estimated_lift"),
        },
        trace_id,
    )


async def log_decision(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    decision: dict[str, Any],
    trace_id: str,
) -> None:
    """Record the chosen arm and how many alternatives it beat."""
    await log_agent_step(
        supabase_client,
        case_id,
        merchant_id,
        "decide",
        "agent",
        "decision_made",
        {
            "chosen_arm": decision.get("chosen_arm"),
            "action_type": decision.get("action_type"),
            "decision_source": decision.get("decision_source"),
            "reasoning": decision.get("reasoning"),
            "alternatives_count": len(decision.get("alternatives_considered", [])),
        },
        trace_id,
    )


async def log_guardrail(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    guardrail: dict[str, Any],
    trace_id: str,
) -> None:
    """Record the verdict and the full check list that produced it.

    ``actor`` is ``system``, not ``agent``: the guardrail is not something the
    agent chose to do, and the distinction matters when reading the trail back.
    """
    verdict = str(guardrail.get("verdict", "unknown"))
    await log_agent_step(
        supabase_client,
        case_id,
        merchant_id,
        "guardrail",
        "system",
        f"guardrail_{verdict.lower()}",
        {
            "verdict": verdict,
            "checks": guardrail.get("checks"),
            "blocking_check": guardrail.get("blocking_check"),
        },
        trace_id,
    )


async def log_execution(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    execution: dict[str, Any],
    trace_id: str,
) -> None:
    """Record what was attempted, through which adapter, and whether it was real."""
    await log_agent_step(
        supabase_client,
        case_id,
        merchant_id,
        "execute",
        "agent",
        "execution_attempted",
        {
            "action_type": execution.get("action_type"),
            "adapter": execution.get("adapter"),
            "status": execution.get("status"),
            "simulated": execution.get("simulated", True),
            "idempotency_key": execution.get("idempotency_key"),
        },
        trace_id,
    )


async def log_listen(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    listen: dict[str, Any],
    trace_id: str,
) -> None:
    """Record how an inbound reply was classified and what it implies."""
    await log_agent_step(
        supabase_client,
        case_id,
        merchant_id,
        "listen",
        "agent",
        "reply_classified",
        {
            "intent": listen.get("intent"),
            "opt_out_signal": listen.get("opt_out_signal"),
            "hardship_signal": listen.get("hardship_signal"),
            "churn_signal": listen.get("churn_signal"),
            "recommended_state_update": listen.get("recommended_state_update"),
        },
        trace_id,
    )


async def log_case_closed(
    supabase_client: Any,
    case_id: str,
    merchant_id: str,
    final_status: str,
    reason: str,
    trace_id: str,
) -> None:
    """Record the terminal state of a case and why it got there."""
    await log_agent_step(
        supabase_client,
        case_id,
        merchant_id,
        "audit",
        "system",
        "case_closed",
        {"final_status": final_status, "reason": reason},
        trace_id,
    )
