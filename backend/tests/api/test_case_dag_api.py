"""The causal graph endpoint.

It serves the picture behind the word "why" on a case. The properties that
matter are that the graph it returns is the one the diagnosis actually ran
against, and that a case with nothing to show says so rather than handing the
UI an empty canvas.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.causal_dag import DAGS
from app.agent.causal_dag.definitions import DAG_VERSION
from app.deps import get_current_user_id, get_user_supabase
from app.main import app
from tests.simulator.conftest import MERCHANT_ID, OTHER_MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase

FEATURES = {
    "insufficient_funds_code": True,
    "failure_on_1st_dom": True,
    "manual_recovery_on_day_4_to_8": True,
    "mandate_revoked_code": False,
}


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    fake.seed_merchant(OTHER_MERCHANT_ID)
    return fake


@pytest.fixture
def client(db: FakeSupabase) -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def add_case(
    db: FakeSupabase,
    *,
    case_id: str = "case-1",
    playbook: str = "subscription_failure",
    diagnosis: dict[str, Any] | None = None,
    merchant: str = MERCHANT_ID,
) -> None:
    db.rows("recovery_cases").append(
        {
            "id": case_id,
            "merchant_id": merchant,
            "playbook": playbook,
            "status": "in_flight",
            "diagnosis": diagnosis,
        }
    )


def diagnosed() -> dict[str, Any]:
    return {
        "root_cause": "salary_cycle_mismatch_with_competing_emi",
        "dag_traversal_used": True,
        "observed_features": FEATURES,
    }


# ── Structure ──────────────────────────────────────────────────────────


def test_the_graph_comes_back_whole(client: TestClient, db: FakeSupabase) -> None:
    add_case(db, diagnosis=diagnosed())

    body = client.get("/api/cases/case-1/dag").json()

    dag = DAGS["subscription_failure"]
    assert body["playbook"] == "subscription_failure"
    assert body["dag_version"] == DAG_VERSION
    assert len(body["nodes"]) == len(dag.nodes)
    assert {node["node_type"] for node in body["nodes"]} == {"observable", "root_cause"}
    assert body["edges"]


def test_every_edge_joins_two_nodes_that_are_present(client: TestClient, db: FakeSupabase) -> None:
    """The frontend lays these out with dagre. An edge naming a node that is not
    in the payload is a crash in the layout pass, not a missing line."""
    add_case(db, diagnosis=diagnosed())

    body = client.get("/api/cases/case-1/dag").json()

    ids = {node["node_id"] for node in body["nodes"]}
    for edge in body["edges"]:
        assert edge["from"] in ids
        assert edge["to"] in ids


def test_root_causes_carry_priors_and_observables_carry_base_rates(
    client: TestClient, db: FakeSupabase
) -> None:
    add_case(db, diagnosis=diagnosed())

    body = client.get("/api/cases/case-1/dag").json()

    for node in body["nodes"]:
        if node["node_type"] == "root_cause":
            assert node["prior_probability"] is not None
        else:
            assert node["base_rate"] is not None


# ── Traversal ──────────────────────────────────────────────────────────


def test_the_traversal_reproduces_what_the_agent_concluded(
    client: TestClient, db: FakeSupabase
) -> None:
    """Recomputed from the stored features rather than read back.

    The diagnosis row keeps the winner and its probability but not the full
    distribution, and the sidebar charts all of them. Deterministic, so it
    cannot disagree — and if it ever did, the graph changed under a closed case.
    """
    add_case(db, diagnosis=diagnosed())

    traversal = client.get("/api/cases/case-1/dag").json()["traversal"]

    assert traversal["root_cause"] == "salary_cycle_mismatch_with_competing_emi"
    assert traversal["posterior_probability"] > 0.80
    assert traversal["observed_features"] == FEATURES
    assert sum(traversal["posteriors"].values()) == pytest.approx(1.0, abs=1e-3)


def test_the_posteriors_cover_every_root_cause_the_sidebar_charts(
    client: TestClient, db: FakeSupabase
) -> None:
    add_case(db, diagnosis=diagnosed())

    body = client.get("/api/cases/case-1/dag").json()

    causes = {n["node_id"] for n in body["nodes"] if n["node_type"] == "root_cause"}
    assert set(body["traversal"]["posteriors"]) == causes


def test_the_causal_path_only_names_nodes_in_the_payload(
    client: TestClient, db: FakeSupabase
) -> None:
    add_case(db, diagnosis=diagnosed())

    body = client.get("/api/cases/case-1/dag").json()

    ids = {node["node_id"] for node in body["nodes"]}
    assert body["traversal"]["causal_path"]
    assert set(body["traversal"]["causal_path"]) <= ids


# ── Nothing to show ────────────────────────────────────────────────────


def test_a_case_diagnosed_before_phase_12_has_a_graph_but_no_traversal(
    client: TestClient, db: FakeSupabase
) -> None:
    """The tab is hidden on this, rather than rendering an unlit canvas."""
    add_case(db, diagnosis={"root_cause": "card_expired", "is_stub": True})

    body = client.get("/api/cases/case-1/dag").json()

    assert body["traversal"] is None
    assert body["nodes"]


def test_an_undiagnosed_case_returns_null_traversal(client: TestClient, db: FakeSupabase) -> None:
    add_case(db, diagnosis=None)

    assert client.get("/api/cases/case-1/dag").json()["traversal"] is None


def test_a_playbook_with_no_graph_is_a_404(client: TestClient, db: FakeSupabase) -> None:
    add_case(db, playbook="not_a_playbook", diagnosis=diagnosed())

    assert client.get("/api/cases/case-1/dag").status_code == 404


# ── Scoping ────────────────────────────────────────────────────────────


def test_another_merchants_case_is_not_found(client: TestClient, db: FakeSupabase) -> None:
    """RLS hides it in production; "not found" and "not yours" are the same
    answer, and 404 is the right one for both."""
    add_case(db, diagnosis=diagnosed(), merchant=OTHER_MERCHANT_ID)

    assert client.get("/api/cases/case-1/dag").status_code == 404


def test_an_unknown_case_is_a_404(client: TestClient) -> None:
    assert client.get("/api/cases/nope/dag").status_code == 404


def test_the_endpoint_requires_authentication() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/cases/case-1/dag").status_code in (401, 403)
