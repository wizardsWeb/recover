"""Counting what the graph's likelihoods claim, against what actually happens.

Every likelihood in `definitions.py` is a person's estimate. This module builds
the evidence that would eventually replace them: for each closed case, how often
the diagnosed cause was accompanied by each symptom.

**What gets counted, and why not what the plan said.** The obvious reading is to
walk consecutive pairs of the causal path and count each as a transition. But
the path is `[symptom, symptom, symptom, cause]` and the graph's arrows all run
`cause → symptom` — so consecutive pairs of a path are not edges of this graph
at all, and rows keyed on them would accumulate against edges that do not exist.

What is recorded instead is the thing the columns are named for. For the
diagnosed cause, every observable the DAG asks about gets `total_observations`
incremented, and the ones that actually fired also get `observed_transitions`.
The ratio is then a direct empirical estimate of `P(symptom | cause)` — the
same quantity the hand-written table holds, gathered from real cases, ready to
be compared against it. Incrementing both counters together (the literal
instruction) would fix every ratio at 1.0 and measure nothing.

**Read-modify-write, not atomic.** Two passes closing the same case's cause
concurrently can lose one increment. That matches how `bandit_posteriors` is
maintained, and the cost is the same: a count that is occasionally one low, in a
table nothing reads yet. Doing it properly needs a Postgres function, which is
the right fix for both when either starts driving a decision.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, cast

from app.agent.causal_dag.definitions import get_dag
from app.logging import get_logger

logger = get_logger(__name__)


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], getattr(result, "data", None) or [])


def _bump(
    supabase_client: Any,
    merchant_id: str,
    playbook: str,
    from_node: str,
    to_node: str,
    *,
    observed: bool,
) -> None:
    """Add one observation to an edge's counters, creating the row if needed."""
    existing = _rows(
        supabase_client.table("causal_edge_updates")
        .select("id, observed_transitions, total_observations")
        .eq("merchant_id", merchant_id)
        .eq("playbook", playbook)
        .eq("from_node", from_node)
        .eq("to_node", to_node)
        .limit(1)
        .execute()
    )
    now = datetime.now(UTC).isoformat()

    if existing:
        row = existing[0]
        supabase_client.table("causal_edge_updates").update(
            {
                "observed_transitions": int(row.get("observed_transitions") or 0) + int(observed),
                "total_observations": int(row.get("total_observations") or 0) + 1,
                "last_updated_at": now,
                "updated_at": now,
            }
        ).eq("id", row["id"]).execute()
        return

    supabase_client.table("causal_edge_updates").insert(
        {
            "merchant_id": merchant_id,
            "playbook": playbook,
            "from_node": from_node,
            "to_node": to_node,
            "observed_transitions": int(observed),
            "total_observations": 1,
            "last_updated_at": now,
        }
    ).execute()


def record_dag_edges(
    supabase_client: Any,
    merchant_id: str,
    playbook: str,
    diagnosis: dict[str, Any],
) -> int:
    """Fold one closed case's diagnosis into the empirical edge counts.

    Synchronous — the Supabase client blocks — and returns how many edges were
    touched. Never raises: this runs after the recovery is already done, and a
    statistics table must not be able to fail a pass whose useful work is
    complete.
    """
    dag = get_dag(playbook)
    root_cause = str(diagnosis.get("root_cause") or "")
    if dag is None or not root_cause or dag.node(root_cause) is None:
        return 0

    observed = diagnosis.get("observed_features")
    if not isinstance(observed, dict):
        # Pre-Phase-12 diagnoses, and LLM-only ones, carry no feature dict.
        # There is nothing to count and inventing a default would poison the
        # very table this exists to make trustworthy.
        return 0

    touched = 0
    for node in dag.observables:
        seen = observed.get(node.node_id)
        if seen is None:
            # Not established for this case. Counting it as a non-occurrence
            # would bias every likelihood downwards by however often the fact
            # was simply unavailable.
            continue
        try:
            _bump(
                supabase_client,
                merchant_id,
                playbook,
                root_cause,
                node.node_id,
                observed=bool(seen),
            )
            touched += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "causal_edge_update_failed",
                playbook=playbook,
                from_node=root_cause,
                to_node=node.node_id,
                error=str(exc),
            )

    logger.info("causal_edges_recorded", playbook=playbook, root_cause=root_cause, edges=touched)
    return touched


async def update_dag_edges(
    supabase_client: Any,
    merchant_id: str,
    playbook: str,
    diagnosis: dict[str, Any],
) -> int:
    """Record the edges off the event loop. Swallows everything."""
    if supabase_client is None:
        return 0
    try:
        return await asyncio.to_thread(
            record_dag_edges, supabase_client, merchant_id, playbook, diagnosis
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("causal_edge_update_error", playbook=playbook, error=str(exc))
        return 0
