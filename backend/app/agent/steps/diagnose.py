"""Step 2 — Diagnose: why is this money at risk?

Phase 4 answers with a fixed hypothesis per playbook. That is not a placeholder
for its own sake — it is the honest state of the system before the LLM lands,
and every stub carries ``is_stub=True`` so the audit trail and the UI can say
"the agent has not reasoned about this yet" instead of presenting a fabricated
posterior as evidence.

Phase 5 replaces ``run_diagnose`` with:

1. causal DAG traversal over ``causal_dag`` to enumerate candidate causes, and
2. a Gemini call that extracts evidence from the event payload and history,

which will fill the same ``DiagnosisResult`` fields with real numbers. The
shape does not change; only ``is_stub`` and the values do.
"""

from typing import Any

from app.agent.models import DiagnosisResult

# These are stub diagnoses keyed by playbook.
# Phase 5 replaces this with real Gemini LLM calls + causal DAG traversal.
STUB_DIAGNOSES: dict[str, DiagnosisResult] = {
    "failed_payment": DiagnosisResult(
        root_cause="issuer_transient_failure",
        posterior_probability=0.70,
        causal_path=["payment.failed", "authentication_failed", "issuer_transient_failure"],
        supporting_evidence=["Stub diagnosis — LLM not yet wired (Phase 5)"],
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
        supporting_evidence=["Stub diagnosis — LLM not yet wired (Phase 5)"],
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
        supporting_evidence=["Stub diagnosis — LLM not yet wired (Phase 5)"],
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
        supporting_evidence=["Stub diagnosis — LLM not yet wired (Phase 5)"],
        alternative_hypotheses=[
            {"cause": "invoice_dispute", "probability": 0.12},
        ],
        risk_factors=[],
        is_stub=True,
    ),
}


async def run_diagnose(case: dict[str, Any], playbook: str) -> DiagnosisResult:
    """Return a stub diagnosis for now.

    Phase 5 replaces this with:
      1. Causal DAG traversal
      2. Gemini LLM evidence extraction

    The result is deep-copied out of ``STUB_DIAGNOSES``. Handing back the shared
    instance would let one case's caller append to another case's
    ``risk_factors`` — a class of bug that is invisible in a single-case test
    and obvious in production.
    """
    stub = STUB_DIAGNOSES.get(playbook, STUB_DIAGNOSES["failed_payment"])
    return stub.model_copy(deep=True)
