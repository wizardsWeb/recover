"""Step 2 — Diagnose: why is this money at risk?

Gemini extracts the root cause from the case context; the fixed hypotheses below
are what answers when it cannot. That split is the whole design of this module.

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

from app.agent.llm import make_gemini_client
from app.agent.models import DiagnosisResult
from app.agent.prompts.diagnose_prompt import DIAGNOSE_SCHEMA, build_diagnose_prompt
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
) -> DiagnosisResult:
    """Extract the root cause with Gemini, falling back to the playbook stub.

    ``supabase_client`` is optional so the step stays callable without a
    database — it is only used for the LLM response cache, and a missing cache
    is a slower call, not a failed one.

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

    # Identity, not equality: `generate_structured` returns the exact dict it
    # was handed on every failure path, so this is the one unambiguous test for
    # "the model did not answer".
    if payload is fallback:
        return stub

    try:
        return DiagnosisResult(**payload, is_stub=False)
    except Exception as exc:  # noqa: BLE001 - a malformed diagnosis must not end the pass
        logger.warning("diagnosis_parse_failed", playbook=playbook, error=str(exc))
        return stub
