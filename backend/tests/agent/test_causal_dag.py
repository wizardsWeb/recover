"""The causal graphs, and the arithmetic over them.

A diagnosis is the most load-bearing sentence this product says to a merchant:
it decides which arm the bandit is choosing among, and it is what appears on the
case detail under the word "why". A wrong one is not a crash — it is a
confident, well-formatted, wrong explanation.

So the tests here fall in three groups: the graphs are internally coherent, the
arithmetic is Bayes, and the extraction reads real fixture payloads correctly.
"""

import pytest

from app.agent.causal_dag import DAGS, extract_observed_features, traverse_dag
from app.agent.causal_dag.definitions import DAG_VERSION, get_dag
from app.simulator import fixtures

# ── The graphs are coherent ────────────────────────────────────────────


@pytest.mark.parametrize("playbook", sorted(DAGS))
def test_priors_are_a_distribution(playbook: str) -> None:
    """They are multiplied into a posterior and normalised against each other.

    Priors summing to 1.2 would not error — every posterior would just be
    quietly wrong in a way no assertion downstream could see.
    """
    dag = DAGS[playbook]
    total = sum(cause.prior_probability or 0.0 for cause in dag.root_causes)

    assert total == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("playbook", sorted(DAGS))
def test_every_probability_is_one(playbook: str) -> None:
    dag = DAGS[playbook]
    for cause in dag.root_causes:
        assert 0.0 < (cause.prior_probability or 0.0) < 1.0
    for observable in dag.observables:
        assert 0.0 < (observable.base_rate or 0.0) <= 1.0
    for cause, table in dag.likelihoods.items():
        for value in table.values():
            assert 0.0 < value < 1.0, cause


@pytest.mark.parametrize("playbook", sorted(DAGS))
def test_likelihood_tables_only_name_nodes_that_exist(playbook: str) -> None:
    """A typo'd node id is silently inert — it would never be looked up, and the
    cause it was meant to distinguish would quietly fall back to base rates."""
    dag = DAGS[playbook]
    causes = {node.node_id for node in dag.root_causes}
    observables = {node.node_id for node in dag.observables}

    for cause, table in dag.likelihoods.items():
        assert cause in causes
        assert set(table) <= observables, f"{cause} names an unknown observable"


@pytest.mark.parametrize("playbook", sorted(DAGS))
def test_node_ids_are_unique(playbook: str) -> None:
    ids = [node.node_id for node in DAGS[playbook].nodes]

    assert len(ids) == len(set(ids))


def test_an_unlisted_pair_falls_back_to_the_base_rate_not_to_zero() -> None:
    """Zero would let one unexpected symptom eliminate a cause outright.

    Nobody wrote a likelihood for "card expired produces a bank downtime
    signal", and the honest reading of that silence is "as often as anything
    else does" — not "never".
    """
    dag = DAGS["subscription_failure"]
    observable = dag.node("bank_downtime_signal")

    assert dag.likelihood("card_expired", "bank_downtime_signal") == observable.base_rate


def test_the_drawn_edges_are_a_readable_subset_not_the_full_product() -> None:
    """Every cause-observable pair has a number; drawing them all is a complete
    bipartite graph, which shows nothing."""
    dag = DAGS["subscription_failure"]
    possible = len(dag.root_causes) * len(dag.observables)

    assert 0 < len(dag.edges) < possible / 2


# ── The arithmetic is Bayes ────────────────────────────────────────────


def test_the_salary_cycle_story_is_recovered_from_its_symptoms() -> None:
    """S1, and the claim the product leads with.

    Three co-symptoms of one story: it failed on the 1st, for want of funds, and
    they paid by hand a few days later. The answer has to be timing, not a
    broken instrument.
    """
    result = traverse_dag(
        "subscription_failure",
        {
            "failure_on_1st_dom": True,
            "insufficient_funds_code": True,
            "manual_recovery_on_day_4_to_8": True,
        },
    )

    assert result["root_cause"] == "salary_cycle_mismatch_with_competing_emi"
    assert result["posterior_probability"] > 0.70
    assert result["dag_version"] == DAG_VERSION


def test_a_network_signal_outvotes_a_much_larger_prior() -> None:
    """The whole point of the cross-merchant view.

    `issuer_transient_failure` starts three and a half times more likely than
    `bank_downtime`. One observation that no single merchant could have made
    alone is what overturns it.
    """
    result = traverse_dag("failed_payment", {"bank_downtime_signal": True})

    assert result["root_cause"] == "bank_downtime"
    assert result["posterior_probability"] > 0.50


@pytest.mark.parametrize("playbook", sorted(DAGS))
def test_posteriors_are_a_distribution(playbook: str) -> None:
    result = traverse_dag(playbook, {})

    assert sum(result["posteriors"].values()) == pytest.approx(1.0, abs=1e-3)


def test_with_no_evidence_the_posterior_is_the_prior() -> None:
    """The property that makes a prior mean what it says."""
    result = traverse_dag("b2b_overdue", {})
    dag = DAGS["b2b_overdue"]

    for cause in dag.root_causes:
        assert result["posteriors"][cause.node_id] == pytest.approx(
            cause.prior_probability, abs=1e-3
        )


def test_a_false_observation_is_evidence_too() -> None:
    """ "The code was not `MANDATE_REVOKED`" argues against a revoked mandate.

    Skipping False features would throw away half the information in a payload
    and leave every cause resting on the symptoms that happened to fire.
    """
    silent = traverse_dag("subscription_failure", {})
    denied = traverse_dag("subscription_failure", {"mandate_revoked_code": False})

    assert (
        denied["posteriors"]["mandate_revoked_by_customer"]
        < silent["posteriors"]["mandate_revoked_by_customer"]
    )


def test_an_absent_feature_is_not_a_false_one() -> None:
    """The distinction that keeps an unavailable network view from ruling out an
    outage every time it cannot be reached."""
    absent = traverse_dag("failed_payment", {})
    denied = traverse_dag("failed_payment", {"bank_downtime_signal": False})

    assert absent["posteriors"]["bank_downtime"] > denied["posteriors"]["bank_downtime"]


def test_more_agreeing_evidence_raises_confidence() -> None:
    one = traverse_dag("subscription_failure", {"failure_on_1st_dom": True})
    three = traverse_dag(
        "subscription_failure",
        {
            "failure_on_1st_dom": True,
            "insufficient_funds_code": True,
            "manual_recovery_on_day_4_to_8": True,
        },
    )

    assert three["posterior_probability"] > one["posterior_probability"]


def test_the_causal_path_only_names_nodes_the_graph_defines() -> None:
    """It is rendered as a highlighted route through the diagram. A node that is
    not in the graph is a path that cannot be drawn."""
    result = traverse_dag(
        "subscription_failure",
        {"failure_on_1st_dom": True, "insufficient_funds_code": True},
    )
    dag = DAGS["subscription_failure"]

    assert result["causal_path"]
    for node_id in result["causal_path"]:
        assert dag.node(node_id) is not None
    assert result["causal_path"][-1] == result["root_cause"]


def test_the_path_excludes_symptoms_the_winner_does_not_explain() -> None:
    """A True observation the chosen cause makes *less* likely is not support
    for it, and putting it in the path would say otherwise."""
    result = traverse_dag(
        "subscription_failure",
        {
            "failure_on_1st_dom": True,
            "insufficient_funds_code": True,
            "manual_recovery_on_day_4_to_8": True,
            "card_expired_code": True,
        },
    )

    assert result["root_cause"] == "salary_cycle_mismatch_with_competing_emi"
    assert "card_expired_code" not in result["causal_path"]


def test_an_unknown_playbook_degrades_rather_than_raising() -> None:
    """The loop must still run for a playbook nobody has drawn a graph for."""
    result = traverse_dag("not_a_playbook", {"anything": True})

    assert result["dag_available"] is False
    assert result["root_cause"] == "unknown"


def test_a_feature_the_graph_does_not_know_is_ignored() -> None:
    result = traverse_dag("subscription_failure", {"invented_feature": True})

    assert result["posteriors"]["salary_cycle_mismatch_with_competing_emi"] == pytest.approx(
        0.35, abs=1e-3
    )


# ── Extraction reads real payloads ─────────────────────────────────────


def suresh_case() -> tuple[dict, dict, dict]:
    """S1, from the shipped fixtures rather than a hand-written stand-in.

    The customer is assembled the way `loader` writes it — `past_events_summary`
    folded into `metadata` alongside the persona's own keys. Passing the raw
    persona instead would put the summary one level out from where every reader
    in the agent looks for it, and the test would pass against a shape that
    never reaches production.
    """
    event = {
        "payload": {
            "failure_code": "BAD_REQUEST_ERROR",
            "failure_reason": "insufficient_funds",
            "method": "upi",
            "bank": "ICICI",
            "attempted_at": "2026-09-01T10:32:14+05:30",
        }
    }
    persona = fixtures.PERSONA_SURESH
    customer = {
        "metadata": {
            **(persona.get("metadata") or {}),
            "past_events_summary": persona["past_events_summary"],
        }
    }
    return {"metadata": {}}, customer, event


def test_sureshs_event_yields_the_features_the_story_rests_on() -> None:
    case, customer, event = suresh_case()

    features = extract_observed_features(case, customer, event, "subscription_failure")

    assert features["failure_on_1st_dom"] is True
    assert features["insufficient_funds_code"] is True
    assert features["manual_recovery_on_day_4_to_8"] is True
    assert features["failure_on_1st_for_3_months"] is True
    assert features["mandate_revoked_code"] is False


def test_the_first_of_the_month_is_read_in_ist() -> None:
    """A UTC read of 2026-09-01T00:30+05:30 lands on the 31st of August.

    The claim is about their calendar, and the whole diagnosis turns on it.
    """
    event = {"payload": {"attempted_at": "2026-09-01T00:30:00+05:30"}}

    features = extract_observed_features({}, {}, event, "subscription_failure")

    assert features["failure_on_1st_dom"] is True


def test_a_nested_decline_code_is_found() -> None:
    """`payment.failed` hides its codes under `error`; the subscription event
    puts them at the top level. One extractor has to read both."""
    event = {"payload": {"error": {"failure_reason": "insufficient funds in account"}}}

    features = extract_observed_features({}, {}, event, "failed_payment")

    assert features["insufficient_funds_code"] is True


def test_a_night_attempt_is_flagged_for_failed_payments() -> None:
    event = {"payload": {"method": "card", "error": {"attempted_at": "2026-09-06T23:34:12+05:30"}}}

    features = extract_observed_features({}, {}, event, "failed_payment")

    assert features["night_hour_attempt"] is True
    assert features["upi_method"] is False


def test_the_network_signal_is_omitted_unless_the_caller_established_it() -> None:
    """Absent, not False — see the module docstring."""
    unchecked = extract_observed_features({}, {}, {"payload": {}}, "failed_payment")
    checked = extract_observed_features(
        {}, {}, {"payload": {}}, "failed_payment", network_degraded=False
    )

    assert "bank_downtime_signal" not in unchecked
    assert checked["bank_downtime_signal"] is False


def test_extraction_never_emits_a_feature_the_graph_lacks() -> None:
    """Anything it did would be inert, and would read in the audit trail as
    evidence that was weighed and found irrelevant."""
    for playbook, dag in DAGS.items():
        features = extract_observed_features({}, {}, {"payload": {}}, playbook)
        assert set(features) <= {node.node_id for node in dag.observables}


def test_a_missing_payload_yields_no_crash_and_no_invented_evidence() -> None:
    features = extract_observed_features({}, None, None, "checkout_abandonment")

    assert features == {}


def test_end_to_end_suresh_diagnoses_as_a_salary_cycle_mismatch() -> None:
    """Extraction and inference together, on the fixture the demo actually fires."""
    case, customer, event = suresh_case()

    features = extract_observed_features(case, customer, event, "subscription_failure")
    result = traverse_dag("subscription_failure", features)

    assert result["root_cause"] == "salary_cycle_mismatch_with_competing_emi"
    assert result["posterior_probability"] > 0.80


def test_every_playbook_has_a_graph() -> None:
    """A playbook without one falls back to the LLM alone and loses its audit
    trail — quietly, and only for that playbook."""
    from app.agent.playbooks import PLAYBOOK_CONFIGS

    for playbook in PLAYBOOK_CONFIGS:
        assert get_dag(playbook) is not None
