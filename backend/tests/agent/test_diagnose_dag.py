"""Diagnosis as graph-then-annotation.

The inversion this phase is for: the numbers come from a table somebody wrote
down, and the model writes the prose. These tests are mostly about what the
model is *not* allowed to do, because the whole value of the arrangement is that
a fluent answer can no longer overrule a computed one.
"""

from typing import Any

import pytest

from app.agent.prompts.diagnose_prompt import ANNOTATE_SCHEMA
from app.agent.steps import diagnose as module
from app.agent.steps.diagnose import run_diagnose
from app.simulator import fixtures

SURESH_EVENT = {
    "payload": {
        "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "insufficient_funds",
        "method": "upi",
        "bank": "ICICI",
        "attempted_at": "2026-09-01T10:32:14+05:30",
    }
}


def suresh_customer() -> dict[str, Any]:
    persona = fixtures.PERSONA_SURESH
    return {
        "metadata": {
            **(persona.get("metadata") or {}),
            "past_events_summary": persona["past_events_summary"],
        }
    }


class _Client:
    """A Gemini stand-in. `answer=None` means every call fails."""

    def __init__(self, answer: dict[str, Any] | None) -> None:
        self.answer = answer
        self.prompts: list[str] = []
        self.schemas: list[dict[str, Any]] = []

    async def generate_structured(
        self, prompt: str, schema: dict[str, Any], kind: str, fallback: dict[str, Any]
    ) -> dict[str, Any]:
        self.prompts.append(prompt)
        self.schemas.append(schema)
        return fallback if self.answer is None else self.answer


@pytest.fixture
def annotator(monkeypatch: pytest.MonkeyPatch) -> _Client:
    client = _Client(
        {
            "supporting_evidence": ["Failed on the 1st for the fourth month running."],
            "risk_factors": ["Only three months of history."],
            "inferred_salary_date": "7",
        }
    )
    monkeypatch.setattr(module, "make_gemini_client", lambda _: client)
    return client


# ── The graph decides ──────────────────────────────────────────────────


async def test_the_posterior_comes_from_the_graph(annotator: _Client) -> None:
    result = await run_diagnose(
        {"metadata": {}}, "subscription_failure", None, SURESH_EVENT, suresh_customer()
    )

    assert result.root_cause == "salary_cycle_mismatch_with_competing_emi"
    assert result.posterior_probability > 0.80
    assert result.dag_traversal_used is True
    assert result.dag_version == "v1"
    assert result.is_stub is False


async def test_the_model_is_not_given_a_field_it_could_overrule_the_graph_with(
    annotator: _Client,
) -> None:
    """Structural, not persuasive.

    A prompt asking the model not to re-diagnose is a request. A schema with no
    `root_cause` property is a guarantee.
    """
    await run_diagnose(
        {"metadata": {}}, "subscription_failure", None, SURESH_EVENT, suresh_customer()
    )

    assert annotator.schemas[0] is ANNOTATE_SCHEMA
    assert "root_cause" not in ANNOTATE_SCHEMA["properties"]
    assert "posterior_probability" not in ANNOTATE_SCHEMA["properties"]


async def test_a_model_that_names_a_different_cause_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Belt and braces on the schema: even a well-formed contradiction loses."""
    rogue = _Client(
        {
            "supporting_evidence": ["The card has expired."],
            "risk_factors": [],
            "root_cause": "card_expired",
            "posterior_probability": 0.99,
        }
    )
    monkeypatch.setattr(module, "make_gemini_client", lambda _: rogue)

    result = await run_diagnose(
        {"metadata": {}}, "subscription_failure", None, SURESH_EVENT, suresh_customer()
    )

    assert result.root_cause == "salary_cycle_mismatch_with_competing_emi"
    assert result.posterior_probability != 0.99


async def test_the_prompt_carries_the_absent_facts_as_well_as_the_present_ones(
    annotator: _Client,
) -> None:
    """A model told only what fired will explain away anything.

    That the mandate-revoked code is *absent* is part of why the answer is what
    it is, and an annotation written without it reads as a guess.
    """
    await run_diagnose(
        {"metadata": {}}, "subscription_failure", None, SURESH_EVENT, suresh_customer()
    )

    prompt = annotator.prompts[0]
    assert "Facts checked and absent" in prompt
    assert "mandate_revoked_code" in prompt


# ── The model annotates ────────────────────────────────────────────────


async def test_the_evidence_and_risks_come_from_the_model(annotator: _Client) -> None:
    result = await run_diagnose(
        {"metadata": {}}, "subscription_failure", None, SURESH_EVENT, suresh_customer()
    )

    assert result.supporting_evidence == ["Failed on the 1st for the fourth month running."]
    assert result.risk_factors == ["Only three months of history."]
    assert result.inferred_salary_date == "7"


# ── Degrading, in order ────────────────────────────────────────────────


async def test_a_missing_annotation_costs_the_prose_not_the_diagnosis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`is_stub` stays False. The graph reasoned; only the write-up is missing,
    and disclaiming the posterior would tell the UI to doubt a number that is
    exactly as real as it would otherwise have been."""
    monkeypatch.setattr(module, "make_gemini_client", lambda _: _Client(None))

    result = await run_diagnose(
        {"metadata": {}}, "subscription_failure", None, SURESH_EVENT, suresh_customer()
    )

    assert result.is_stub is False
    assert result.dag_traversal_used is True
    assert result.root_cause == "salary_cycle_mismatch_with_competing_emi"
    # Terse and true, rather than an empty panel under the word "why".
    assert result.supporting_evidence
    assert "Observed:" in result.supporting_evidence[0]


async def test_a_playbook_with_no_graph_falls_back_to_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "make_gemini_client", lambda _: _Client(None))

    result = await run_diagnose({"metadata": {}}, "not_a_playbook", None, None, None)

    assert result.dag_traversal_used is False
    assert result.is_stub is True


async def test_the_network_signal_is_only_observed_when_it_was_established(
    annotator: _Client,
) -> None:
    """None leaves the node unobserved; False asserts the rail is healthy."""
    unchecked = await run_diagnose(
        {"metadata": {}}, "failed_payment", None, {"payload": {"method": "card"}}, None
    )
    checked = await run_diagnose(
        {"metadata": {}},
        "failed_payment",
        None,
        {"payload": {"method": "card"}},
        None,
        network_degraded=True,
    )

    assert "bank_downtime_signal" not in unchecked.observed_features
    assert checked.observed_features["bank_downtime_signal"] is True
    assert checked.root_cause == "bank_downtime"


async def test_the_features_travel_with_the_result(annotator: _Client) -> None:
    """The edge recorder and the DAG endpoint both read them off the diagnosis,
    and a case that lost them cannot be explained after the fact."""
    result = await run_diagnose(
        {"metadata": {}}, "subscription_failure", None, SURESH_EVENT, suresh_customer()
    )

    assert result.observed_features["failure_on_1st_dom"] is True
    assert result.observed_features["mandate_revoked_code"] is False


async def test_the_causal_path_is_drawable(annotator: _Client) -> None:
    from app.agent.causal_dag import DAGS

    result = await run_diagnose(
        {"metadata": {}}, "subscription_failure", None, SURESH_EVENT, suresh_customer()
    )

    dag = DAGS["subscription_failure"]
    assert result.causal_path
    for node_id in result.causal_path:
        assert dag.node(node_id) is not None
