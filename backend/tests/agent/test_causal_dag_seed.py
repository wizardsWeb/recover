"""Publishing the graph into `causal_dag`.

The rows are a copy, not the source — the agent reasons from `definitions.py`
and the API serves from there. So the properties worth holding are that the copy
is faithful, that republishing does not fork it, and that nothing about it can
change a diagnosis.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.agent.causal_dag.definitions import DAG_VERSION, DAGS
from app.agent.causal_dag.seed import seed_causal_dag
from app.api import simulator as module
from tests.simulator.conftest import MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase


def test_every_node_of_every_graph_is_published() -> None:
    db = FakeSupabase()

    summary = seed_causal_dag(db)

    expected = sum(len(dag.nodes) for dag in DAGS.values())
    assert summary["nodes"] == expected
    assert len(db.rows("causal_dag")) == expected
    assert summary["dag_version"] == DAG_VERSION


def test_reseeding_updates_in_place_rather_than_forking_the_graph() -> None:
    """Two copies of a node would make "the graph" ambiguous to anyone reading
    the table, which is the only thing the table is for."""
    db = FakeSupabase()

    seed_causal_dag(db)
    seed_causal_dag(db)

    rows = db.rows("causal_dag")
    keys = [(row["playbook"], row["node_id"]) for row in rows]
    assert len(keys) == len(set(keys))


def test_a_composite_conflict_target_matches_on_both_columns() -> None:
    """`node_id` alone is not unique across playbooks.

    `card_expired` is a cause in two graphs with different priors, so an upsert
    keyed on the node alone would leave one playbook holding the other's number.
    """
    db = FakeSupabase()

    seed_causal_dag(db)

    card_expired = [row for row in db.rows("causal_dag") if row["node_id"] == "card_expired"]
    assert {row["playbook"] for row in card_expired} == {
        "subscription_failure",
        "failed_payment",
    }


def test_a_published_node_carries_what_a_sql_reader_would_need() -> None:
    db = FakeSupabase()

    seed_causal_dag(db)

    row = next(
        r
        for r in db.rows("causal_dag")
        if r["node_id"] == "salary_cycle_mismatch_with_competing_emi"
    )
    assert row["node_type"] == "root_cause"
    assert row["prior_probability"] == 0.35
    assert row["metadata"]["label"]
    assert row["metadata"]["likelihoods"]["failure_on_1st_dom"] == 0.85


def test_parents_point_from_symptom_to_cause() -> None:
    """The column's name is Bayesian: a node's parents are what it is
    conditioned on, which is the reverse of how the arrows are drawn."""
    db = FakeSupabase()

    seed_causal_dag(db)

    row = next(
        r
        for r in db.rows("causal_dag")
        if r["playbook"] == "subscription_failure" and r["node_id"] == "failure_on_1st_dom"
    )
    assert "salary_cycle_mismatch_with_competing_emi" in row["parents"]


def test_root_causes_have_no_parents() -> None:
    db = FakeSupabase()

    seed_causal_dag(db)

    for row in db.rows("causal_dag"):
        if row["node_type"] == "root_cause":
            assert row["parents"] == []


# ── The endpoint ───────────────────────────────────────────────────────


@pytest.fixture
def seeded_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, FakeSupabase]]:
    from app.deps import get_current_user_id, get_user_supabase
    from app.main import app

    db = FakeSupabase()
    db.seed_merchant(MERCHANT_ID)
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    monkeypatch.setattr(module, "get_service_client", lambda: db)
    with TestClient(app) as client:
        yield client, db
    app.dependency_overrides.clear()


def test_the_endpoint_publishes_the_graph(
    seeded_client: tuple[TestClient, FakeSupabase],
) -> None:
    client, db = seeded_client

    response = client.post("/api/simulator/dag/seed", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["nodes"] == len(db.rows("causal_dag"))
    assert body["playbooks"] == sorted(DAGS)


def test_the_endpoint_writes_with_the_service_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`causal_dag` grants an authenticated user SELECT and nothing else.

    Writing it through the caller's client fails with 42501 behind an opaque
    500 — the mistake Phase 10's downtime endpoint shipped with. `FakeSupabase`
    does not enforce RLS, so the property is asserted structurally: give the two
    clients separate databases and check which one the rows land in.
    """
    from app.deps import get_current_user_id, get_user_supabase
    from app.main import app

    user_db = FakeSupabase()
    user_db.seed_merchant(MERCHANT_ID)
    service_db = FakeSupabase()
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: user_db
    monkeypatch.setattr(module, "get_service_client", lambda: service_db)

    try:
        with TestClient(app) as client:
            assert client.post("/api/simulator/dag/seed", json={}).status_code == 200
    finally:
        app.dependency_overrides.clear()

    assert service_db.rows("causal_dag")
    assert user_db.rows("causal_dag") == []


def test_the_endpoint_requires_authentication() -> None:
    from app.main import app
    from app.main import app as _app

    _app.dependency_overrides.clear()
    with TestClient(app) as anonymous:
        assert anonymous.post("/api/simulator/dag/seed", json={}).status_code in (401, 403)


def test_publishing_cannot_change_a_diagnosis(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reason authority stays in Python.

    Traversing from the table would put the graph one UPDATE away from changing
    every diagnosis, silently. Corrupting every published row must leave the
    inference untouched.
    """
    from app.agent.causal_dag import traverse_dag

    db = FakeSupabase()
    seed_causal_dag(db)
    for row in db.rows("causal_dag"):
        row["prior_probability"] = 0.99

    result = traverse_dag("subscription_failure", {"insufficient_funds_code": True})

    assert result["root_cause"] == "salary_cycle_mismatch_with_competing_emi"
    assert sum(result["posteriors"].values()) == pytest.approx(1.0, abs=1e-3)
