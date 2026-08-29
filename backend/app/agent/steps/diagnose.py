"""Step 2 — Diagnose: why is this money at risk?

Two stages, and the order of them is the point.

**A causal graph decides.** `extract_observed_features` turns the payload and
the customer's history into booleans; `traverse_dag` multiplies them against
hand-written likelihoods and returns a posterior over named causes. It is
deterministic, sub-millisecond, and the same evidence produces the same answer
every time — which is what makes a diagnosis auditable rather than merely
plausible.

**Then a model explains.** Gemini is handed the conclusion and asked for the
sentences a merchant would recognise. Its schema has no `root_cause` field and
no `posterior_probability` field, so it cannot overrule the graph even if it
disagrees — the constraint is structural, not a matter of the prompt being
firmly enough worded.

That inversion is the whole phase. Before, the model answered "what caused this
and how sure are you", and both halves were unfalsifiable: a fluent invention is
indistinguishable from an inference. Now the numbers come from a table somebody
wrote on purpose, and the model does the part it is genuinely reliable at.

**Three ways this degrades, in order.** A missing annotation costs the evidence
strings and nothing else — the diagnosis is still real, so `is_stub` stays
False. A playbook with no graph falls back to the Phase 5 path, model-led. Both
of those failing lands on the per-playbook fallback below with `is_stub=True`.

``STUB_DIAGNOSES`` is not dead code and is not a placeholder any more — it is the
**fallback**, one per playbook, and it is the most conservative honest answer
available without a model. When it is what comes back, ``is_stub`` stays
``True``, and the audit trail and the UI say "the agent has not reasoned about
this yet" instead of presenting a fabricated posterior as evidence. A Gemini
outage therefore degrades this step to exactly its Phase 4 behaviour rather than
failing the recovery.

Whether the model actually answered is established by object identity, not by
inspecting the result: ``generate_structured`` hands back the very dict it was
given when anything goes wrong, so ``payload is fallback`` is an exact test. A
heuristic on the content ("does this look stubby?") would eventually mislabel a
real diagnosis that happened to agree with the stub.

The prompt is built in ``app.agent.prompts.diagnose_prompt`` and is handed only
the fields it needs. It is never given the case dict wholesale, because
``customer.metadata`` carries the Phase 9 ground truth — true willingness to
pay, the counterfactual recovery date — that nothing in the agent path may read.
"""

from typing import Any

from app.agent.causal_dag import extract_observed_features, traverse_dag
from app.agent.causal_dag.definitions import get_dag
from app.agent.llm import make_gemini_client
from app.agent.models import DiagnosisResult
from app.agent.prompts.diagnose_prompt import (
    ANNOTATE_SCHEMA,
    DIAGNOSE_SCHEMA,
    build_annotate_prompt,
    build_diagnose_prompt,
)
from app.logging import get_logger

logger = get_logger(__name__)

# These are the per-playbook fallbacks, returned with ``is_stub=True`` whenever
# Gemini is unavailable, rate-limited, or answers off-schema.
STUB_DIAGNOSES: dict[str, DiagnosisResult] = {
    "failed_payment": DiagnosisResult(
        root_cause="issuer_transient_failure",
        posterior_probability=0.70,
        causal_path=["payment.failed", "authentication_failed", "issuer_transient_failure"],
        supporting_evidence=["Fallback diagnosis — Gemini unavailable, no evidence extracted"],
        alternative_hypotheses=[
            {"cause": "insufficient_funds", "probability": 0.20},
            {"cause": "card_expired", "probability": 0.10},
        ],
        risk_factors=[],
        is_stub=True,
    ),
    "checkout_abandonment": DiagnosisResult(
        root_cause="price_sensitivity_at_checkout",
        posterior_probability=0.65,
        causal_path=[
            "checkout.abandoned",
            "dropped_at_method_selection",
            "price_sensitivity_at_checkout",
        ],
        supporting_evidence=["Fallback diagnosis — Gemini unavailable, no evidence extracted"],
        alternative_hypotheses=[
            {"cause": "distracted_multitasking", "probability": 0.25},
        ],
        risk_factors=[],
        is_stub=True,
    ),
    "subscription_failure": DiagnosisResult(
        root_cause="salary_cycle_mismatch",
        posterior_probability=0.75,
        causal_path=["subscription.charged.failed", "insufficient_funds", "salary_cycle_mismatch"],
        supporting_evidence=["Fallback diagnosis — Gemini unavailable, no evidence extracted"],
        alternative_hypotheses=[
            {"cause": "mandate_revoked", "probability": 0.15},
        ],
        risk_factors=["High LTV customer — avoid aggressive tone"],
        inferred_salary_date=None,
        is_stub=True,
    ),
    "b2b_overdue": DiagnosisResult(
        root_cause="chronic_late_payment_pattern",
        posterior_probability=0.80,
        causal_path=["invoice.overdue", "chronic_late_payment_pattern"],
        supporting_evidence=["Fallback diagnosis — Gemini unavailable, no evidence extracted"],
        alternative_hypotheses=[
            {"cause": "invoice_dispute", "probability": 0.12},
        ],
        risk_factors=[],
        is_stub=True,
    ),
}


async def run_diagnose(
    case: dict[str, Any],
    playbook: str,
    supabase_client: Any = None,
    event: dict[str, Any] | None = None,
    customer: dict[str, Any] | None = None,
    *,
    network_degraded: bool | None = None,
) -> DiagnosisResult:
    """Diagnose the case: causal graph first, model second.

    ``supabase_client`` is optional so the step stays callable without a
    database — it is only used for the LLM response cache, and a missing cache
    is a slower call, not a failed one.

    ``network_degraded`` is the one observable that needs I/O to settle, so the
    caller establishes it and passes it in. Left as None it is simply not
    observed, which is different from observing that the bank is healthy.
    """
    if get_dag(playbook) is None:
        # No graph for this playbook. Fall back to the model-led path rather
        # than refusing to diagnose.
        return await _diagnose_with_llm(case, playbook, supabase_client, event, customer)

    features = extract_observed_features(
        case, customer, event, playbook, network_degraded=network_degraded
    )
    traversal = traverse_dag(playbook, features)

    annotation = await _annotate(case, customer, event, supabase_client, traversal, features)

    logger.info(
        "diagnosis_complete",
        playbook=playbook,
        root_cause=traversal["root_cause"],
        posterior=traversal["posterior_probability"],
        features_observed=len(features),
        annotated=annotation is not None,
    )

    return DiagnosisResult(
        root_cause=str(traversal["root_cause"]),
        posterior_probability=float(traversal["posterior_probability"]),
        causal_path=list(traversal["causal_path"]),
        alternative_hypotheses=list(traversal["alternative_hypotheses"]),
        supporting_evidence=(
            list(annotation.get("supporting_evidence") or [])
            if annotation
            else _evidence_from_features(features)
        ),
        risk_factors=list(annotation.get("risk_factors") or []) if annotation else [],
        inferred_salary_date=(annotation or {}).get("inferred_salary_date"),
        dag_traversal_used=True,
        observed_features=features,
        dag_version=str(traversal["dag_version"]),
        # The graph reasoned. A missing annotation costs the prose, not the
        # inference, and calling that a stub would tell the UI to disclaim a
        # posterior that is exactly as real as it would otherwise have been.
        is_stub=False,
    )


def _evidence_from_features(features: dict[str, bool]) -> list[str]:
    """What to say when the model could not be reached.

    Reads the observed node labels back out of the graph rather than inventing
    a sentence. Terse, and true — which is the right trade when the alternative
    is an empty panel under the word "why".
    """
    from app.agent.causal_dag.definitions import DAGS

    labels: dict[str, str] = {
        node.node_id: node.label for dag in DAGS.values() for node in dag.observables
    }
    fired = [labels.get(name, name) for name, seen in features.items() if seen]
    if not fired:
        return ["Diagnosed from the causal model; no annotation available."]
    return [f"Observed: {', '.join(fired)}."]


async def _annotate(
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    event: dict[str, Any] | None,
    supabase_client: Any,
    traversal: dict[str, Any],
    features: dict[str, bool],
) -> dict[str, Any] | None:
    """Ask the model to explain the graph's conclusion. None if it could not."""
    fallback: dict[str, Any] = {"supporting_evidence": [], "risk_factors": []}
    client = make_gemini_client(supabase_client)
    prompt = build_annotate_prompt(
        case,
        customer,
        event,
        root_cause=str(traversal["root_cause"]),
        posterior_probability=float(traversal["posterior_probability"]),
        observed_features=features,
    )
    payload = await client.generate_structured(prompt, ANNOTATE_SCHEMA, "diagnose", fallback)

    # Identity, not equality: `generate_structured` returns the exact dict it
    # was handed on every failure path.
    return None if payload is fallback else payload


async def _diagnose_with_llm(
    case: dict[str, Any],
    playbook: str,
    supabase_client: Any,
    event: dict[str, Any] | None,
    customer: dict[str, Any] | None,
) -> DiagnosisResult:
    """The Phase 5 path, for a playbook with no causal graph.

    The stub is deep-copied on every path. Handing back the shared instance
    would let one case's caller append to another case's ``risk_factors`` — a
    class of bug that is invisible in a single-case test and obvious in
    production.
    """
    stub = STUB_DIAGNOSES.get(playbook, STUB_DIAGNOSES["failed_payment"]).model_copy(deep=True)

    fallback = stub.model_dump(mode="json", exclude={"is_stub"})
    client = make_gemini_client(supabase_client)
    prompt = build_diagnose_prompt(case, customer, event)
    payload = await client.generate_structured(prompt, DIAGNOSE_SCHEMA, "diagnose", fallback)

    if payload is fallback:
        return stub

    try:
        return DiagnosisResult(**payload, is_stub=False)
    except Exception as exc:  # noqa: BLE001 - a malformed diagnosis must not end the pass
        logger.warning("diagnosis_parse_failed", playbook=playbook, error=str(exc))
        return stub
