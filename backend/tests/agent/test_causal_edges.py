"""Recording what the graph claimed, against what happened.

The table this writes is the evidence that would eventually replace the
hand-written likelihoods, so the failure that matters is not a crash — it is a
count that looks like data and is not. Every test here is about a way that
could happen.
"""

from typing import Any

from app.agent.causal_dag import DAGS
from app.agent.causal_dag.edges import record_dag_edges, update_dag_edges
from tests.simulator.fake_supabase import FakeSupabase

MERCHANT = "11111111-1111-4111-8111-111111111111"
PLAYBOOK = "subscription_failure"


def diagnosis(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "root_cause": "salary_cycle_mismatch_with_competing_emi",
        "observed_features": {
            "insufficient_funds_code": True,
            "failure_on_1st_dom": True,
            "mandate_revoked_code": False,
        },
    }
    base.update(overrides)
    return base


def edges(db: FakeSupabase) -> dict[str, tuple[int, int]]:
    return {
        row["to_node"]: (row["observed_transitions"], row["total_observations"])
        for row in db.rows("causal_edge_updates")
    }


# ── What gets counted ──────────────────────────────────────────────────


def test_a_fired_symptom_counts_towards_both_numerator_and_denominator() -> None:
    db = FakeSupabase()

    record_dag_edges(db, MERCHANT, PLAYBOOK, diagnosis())

    assert edges(db)["insufficient_funds_code"] == (1, 1)


def test_a_symptom_that_did_not_fire_counts_only_in_the_denominator() -> None:
    """The whole point of the pair.

    Incrementing both together — the literal instruction — fixes every ratio at
    1.0, and a table where `P(symptom | cause)` is always one measures nothing.
    """
    db = FakeSupabase()

    record_dag_edges(db, MERCHANT, PLAYBOOK, diagnosis())

    assert edges(db)["mandate_revoked_code"] == (0, 1)


def test_the_ratio_converges_on_the_empirical_likelihood() -> None:
    """Three cases where the symptom fired twice should read as two in three."""
    db = FakeSupabase()

    for fired in (True, True, False):
        record_dag_edges(
            db,
            MERCHANT,
            PLAYBOOK,
            diagnosis(observed_features={"insufficient_funds_code": fired}),
        )

    observed, total = edges(db)["insufficient_funds_code"]
    assert (observed, total) == (2, 3)


def test_edges_are_recorded_against_the_cause_not_between_symptoms() -> None:
    """Consecutive pairs of a causal path are not edges of a bipartite graph.

    Keying rows on them would accumulate counts against arrows the DAG does not
    contain, in a table whose whole purpose is to be comparable with it.
    """
    db = FakeSupabase()

    record_dag_edges(db, MERCHANT, PLAYBOOK, diagnosis())

    dag = DAGS[PLAYBOOK]
    causes = {node.node_id for node in dag.root_causes}
    observables = {node.node_id for node in dag.observables}
    for row in db.rows("causal_edge_updates"):
        assert row["from_node"] in causes
        assert row["to_node"] in observables


def test_an_undetermined_symptom_is_not_counted_as_absent() -> None:
    """Counting it would bias every likelihood down by however often the fact
    was simply unavailable — the network signal, most of the time."""
    db = FakeSupabase()

    record_dag_edges(
        db, MERCHANT, PLAYBOOK, diagnosis(observed_features={"failure_on_1st_dom": True})
    )

    assert set(edges(db)) == {"failure_on_1st_dom"}


# ── What is refused ────────────────────────────────────────────────────


def test_a_diagnosis_with_no_features_records_nothing() -> None:
    """LLM-only and pre-Phase-12 diagnoses. Defaulting them to all-false would
    poison the table this exists to make trustworthy."""
    db = FakeSupabase()

    assert record_dag_edges(db, MERCHANT, PLAYBOOK, {"root_cause": "card_expired"}) == 0
    assert db.rows("causal_edge_updates") == []


def test_a_cause_the_graph_does_not_define_records_nothing() -> None:
    db = FakeSupabase()

    assert record_dag_edges(db, MERCHANT, PLAYBOOK, diagnosis(root_cause="invented")) == 0


def test_an_unknown_playbook_records_nothing() -> None:
    assert record_dag_edges(FakeSupabase(), MERCHANT, "not_a_playbook", diagnosis()) == 0


def test_rows_are_scoped_to_the_merchant() -> None:
    db = FakeSupabase()

    record_dag_edges(db, MERCHANT, PLAYBOOK, diagnosis())

    assert {row["merchant_id"] for row in db.rows("causal_edge_updates")} == {MERCHANT}


# ── Failure is contained ───────────────────────────────────────────────


async def test_a_broken_table_does_not_fail_the_pass() -> None:
    """This runs after the recovery has already happened. A statistics write
    must not be able to undo work that is complete."""

    class Broken:
        def table(self, name: str) -> Any:
            raise ConnectionError("supabase unavailable")

    assert await update_dag_edges(Broken(), MERCHANT, PLAYBOOK, diagnosis()) == 0


async def test_one_failing_edge_does_not_stop_the_others() -> None:
    calls = {"n": 0}

    class Flaky(FakeSupabase):
        def table(self, name: str) -> Any:
            if name == "causal_edge_updates":
                calls["n"] += 1
                if calls["n"] == 1:
                    raise ConnectionError("transient")
            return super().table(name)

    db = Flaky()
    touched = await update_dag_edges(db, MERCHANT, PLAYBOOK, diagnosis())

    assert touched == 2


async def test_no_client_is_a_no_op() -> None:
    assert await update_dag_edges(None, MERCHANT, PLAYBOOK, diagnosis()) == 0
