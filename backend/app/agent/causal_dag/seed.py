"""Publishing the graph definitions into `causal_dag`.

The table is not what the agent reasons from — `definitions.py` is, and the API
serves from there too, so that a merchant never sees a diagram that does not
explain their own case. What the rows are for is everything *around* the
inference: reading the encoded domain knowledge with a SQL client, diffing two
versions of it, and giving `causal_edge_updates` a set of nodes its counts can
be joined against.

Keeping the authority in Python and the copy in Postgres is deliberate. The
alternative — traversing from the table — would put a graph the agent has never
validated one `UPDATE` away from changing every diagnosis, silently.

Global reference data, like `bandit_arms` and `causal_dag`'s own RLS policy
says: readable by any authenticated user, written by the service role only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from app.agent.causal_dag.definitions import DAG_VERSION, DAGS
from app.logging import get_logger

logger = get_logger(__name__)


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], getattr(result, "data", None) or [])


def _node_rows() -> list[dict[str, Any]]:
    """Every node of every graph, as `causal_dag` rows.

    `parents` holds the causes that produce an observable, which is the reverse
    of how the arrows are drawn and the right direction for the column's name: a
    parent in a Bayesian network is what a node is conditioned on. Root causes
    have none — they are the roots.
    """
    now = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []

    for playbook, dag in DAGS.items():
        parents: dict[str, list[str]] = {node.node_id: [] for node in dag.observables}
        for edge in dag.edges:
            parents[edge.to_node].append(edge.from_node)

        for node in dag.nodes:
            rows.append(
                {
                    "playbook": playbook,
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "parents": parents.get(node.node_id, []),
                    "prior_probability": node.prior_probability,
                    "metadata": {
                        "label": node.label,
                        "description": node.description,
                        "base_rate": node.base_rate,
                        "dag_version": DAG_VERSION,
                        # The likelihoods this node participates in, so the row
                        # is self-contained for anyone reading the table rather
                        # than the module.
                        "likelihoods": (
                            {
                                edge.to_node: edge.likelihood
                                for edge in dag.edges
                                if edge.from_node == node.node_id
                            }
                            if node.node_type == "root_cause"
                            else {}
                        ),
                    },
                    "updated_at": now,
                }
            )
    return rows


def seed_causal_dag(supabase_client: Any) -> dict[str, Any]:
    """Upsert every node. Safe to run repeatedly.

    Takes the **service-role** client: `causal_dag` is global reference data
    with no merchant column, so there is no RLS policy a user client could
    satisfy for a write.

    Upserted on `(playbook, node_id)`, the table's own unique constraint, so a
    reload after editing a likelihood updates in place rather than accumulating
    a second copy of the graph.
    """
    rows = _node_rows()
    written = _rows(
        supabase_client.table("causal_dag").upsert(rows, on_conflict="playbook,node_id").execute()
    )

    logger.info(
        "causal_dag_seeded",
        nodes=len(rows),
        written=len(written),
        playbooks=len(DAGS),
        dag_version=DAG_VERSION,
    )
    return {
        "nodes": len(rows),
        "playbooks": sorted(DAGS),
        "dag_version": DAG_VERSION,
    }
