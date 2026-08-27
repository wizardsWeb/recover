"""Prompt and schema for step 2 — root-cause extraction.

The job here is *extraction*, not diagnosis-from-nothing. Everything the model
is allowed to conclude from is in the prompt: the failure code, the bank's
recent success rate, how many times this customer has failed before, and which
days of the month they historically recovered on. The instruction block says so
explicitly, because the failure mode that matters is not a wrong root cause —
it is a confident, fluent, invented one that lands in an audit trail a merchant
will read as fact.

``root_cause`` is a closed enum rather than free text for the same reason. The
UI maps it to a human label, the bandit will eventually condition on it, and a
model that can write anything will eventually write ``salary_cycle_mismatch_``
``with_competing_emi_and_festival_spending`` once and break both.

Schema note: this is Gemini's OpenAPI-3.0 subset, not JSON Schema. No
``$schema``, no ``additionalProperties``, no union types — ``nullable: true``
carries optionality, and ``propertyOrdering`` fixes generation order so the
posterior is written *after* the evidence that justifies it rather than before.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

#: The closed set of causes the diagnosis may name.
#:
#: Drawn from the four playbooks' failure modes plus the ones scenarios.md
#: actually asserts. ``unknown`` is last and is a real answer: a model with no
#: evidence should say so rather than pick the most plausible-sounding entry.
ROOT_CAUSES: list[str] = [
    "salary_cycle_mismatch_with_competing_emi",
    "insufficient_funds_transient",
    "issuer_transient_failure",
    "bank_downtime",
    "network_wide_psp_degradation",
    "mandate_revoked_or_expired",
    "mandate_not_registered",
    "card_expired",
    "account_closed",
    "price_sensitivity_at_checkout",
    "distracted_multitasking",
    "comparing_across_apps",
    "trust_hesitation_new_merchant",
    "payment_method_unavailable_at_checkout",
    "chronic_late_payment_pattern",
    "invoice_dispute",
    "customer_churn_intent",
    "technical_issue_unlogged",
    "unknown",
]

DIAGNOSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "supporting_evidence": {
            "type": "ARRAY",
            "description": (
                "Facts from the context that support the root cause. Quote numbers "
                "given in the context. Never state a fact not present above."
            ),
            "items": {"type": "STRING"},
        },
        "causal_path": {
            "type": "ARRAY",
            "description": (
                "Ordered chain from the observed event to the root cause, most "
                "observable first. 2-4 links."
            ),
            "items": {"type": "STRING"},
        },
        "root_cause": {
            "type": "STRING",
            "description": "The single most probable cause, from the allowed set.",
            "enum": ROOT_CAUSES,
        },
        "posterior_probability": {
            "type": "NUMBER",
            "description": (
                "Confidence in root_cause, 0 to 1. Above 0.8 only when several "
                "independent facts agree. Below 0.5 when the context is thin."
            ),
        },
        "alternative_hypotheses": {
            "type": "ARRAY",
            "description": "Other causes still in play, with their probabilities.",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "cause": {"type": "STRING", "enum": ROOT_CAUSES},
                    "probability": {"type": "NUMBER"},
                },
                "required": ["cause", "probability"],
            },
        },
        "risk_factors": {
            "type": "ARRAY",
            "description": (
                "Things that should change how the customer is contacted — high LTV, "
                "long tenure, first failure, time-sensitive service. Empty if none."
            ),
            "items": {"type": "STRING"},
        },
        "inferred_salary_date": {
            "type": "STRING",
            "description": (
                "ISO date (YYYY-MM-DD) the customer's funds most likely arrive, when "
                "the past-recovery days support one. Null otherwise."
            ),
            "nullable": True,
        },
    },
    "required": [
        "supporting_evidence",
        "causal_path",
        "root_cause",
        "posterior_probability",
        "alternative_hypotheses",
        "risk_factors",
        "inferred_salary_date",
    ],
    "propertyOrdering": [
        "supporting_evidence",
        "causal_path",
        "root_cause",
        "posterior_probability",
        "alternative_hypotheses",
        "risk_factors",
        "inferred_salary_date",
    ],
}

#: Returned when the LLM is unavailable and the caller has no better stub.
#:
#: ``unknown`` at 0.3 is the honest shape of "no reasoning happened": callers
#: pair it with ``is_stub=True`` so the UI can say so rather than presenting a
#: fabricated posterior as evidence.
FALLBACK_DIAGNOSIS: dict[str, Any] = {
    "root_cause": "unknown",
    "posterior_probability": 0.3,
    "causal_path": ["event_observed", "unknown"],
    "supporting_evidence": ["LLM unavailable — no evidence extracted"],
    "alternative_hypotheses": [],
    "risk_factors": [],
    "inferred_salary_date": None,
}

#: One worked example, from scenarios.md S1 (Suresh Iyer).
#:
#: A single few-shot is deliberate. The example teaches the *shape* of good
#: evidence — count the failures, name the days, cite the population prior — and
#: adding three would start teaching the content, which is how a checkout
#: abandonment ends up diagnosed as a salary mismatch.
_FEW_SHOT = """\
EXAMPLE

Context:
  playbook: subscription_failure
  event_type: subscription.charged.failed
  failure_code: insufficient_funds
  failure_reason: Insufficient balance in account
  method: upi (autopay mandate)
  bank: ICICI
  amount_inr: 2999
  hour_ist: 10
  day_of_week: Tuesday
  ltv_inr: 27000
  tenure_days: 240
  past_failure_count: 3 (all on the 1st of the month)
  past_recovery_days_of_month: [7, 4, 8]
  bank_success_rate_90d: 0.62

Output:
{
  "supporting_evidence": [
    "3 consecutive failures on the 1st of the month, all with insufficient_funds",
    "Every past manual recovery landed on day 4, 7 or 8 of the month",
    "ICICI UPI success rate of 0.62 is depressed by this customer's own failure \
run, not by a bank-wide issue",
    "240-day tenure with 8 successful charges — this is a paying customer with a \
timing problem"
  ],
  "causal_path": [
    "subscription.charged.failed",
    "insufficient_funds",
    "account_balance_insufficient_at_charge_time",
    "salary_cycle_mismatch_with_competing_emi"
  ],
  "root_cause": "salary_cycle_mismatch_with_competing_emi",
  "posterior_probability": 0.82,
  "alternative_hypotheses": [
    {"cause": "mandate_revoked_or_expired", "probability": 0.09},
    {"cause": "account_closed", "probability": 0.04},
    {"cause": "bank_downtime", "probability": 0.03}
  ],
  "risk_factors": [
    "High LTV customer (Rs 27,000) — avoid aggressive tone",
    "Historical pattern shows willingness to pay, only the timing is wrong"
  ],
  "inferred_salary_date": "2026-09-07"
}

END EXAMPLE
"""

_INSTRUCTIONS = """\
You are the diagnosis step of an Indian revenue-recovery agent. You are given \
one failed or abandoned payment and everything known about it. Name the single \
most probable root cause and the evidence for it.

Rules:
1. Use ONLY facts present in the context below. Do not invent a bank, an amount, \
a date, or a history that is not stated.
2. If a field is missing or "unknown", say the evidence is thin and lower \
posterior_probability accordingly. Do not guess to fill a gap.
3. root_cause and every alternative cause must be one of the allowed enum values.
4. posterior_probability plus the alternative probabilities should roughly sum \
to 1.0.
5. supporting_evidence must quote the numbers you were given, not paraphrase \
them away.
6. inferred_salary_date: set this ONLY when past_recovery_days_of_month cluster \
around a specific part of the month. Otherwise null.
7. Reply with JSON matching the schema. No prose outside the JSON.
"""


def _ist_parts(event: dict[str, Any] | None) -> tuple[str, str]:
    """Return ``(hour_ist, day_of_week)`` for the trigger event.

    Falls back to ``"unknown"`` rather than to *now*: a diagnosis that reasons
    about a Saturday-night failure because the pass happened to run on a
    Saturday night would be confidently wrong, and S3 turns on exactly that
    field.
    """
    if not event:
        return "unknown", "unknown"
    payload = event.get("payload") or {}
    stamp = payload.get("attempted_at") or payload.get("abandoned_at") or event.get("received_at")
    if not stamp:
        return "unknown", "unknown"
    try:
        moment = datetime.fromisoformat(str(stamp)).astimezone(IST)
    except (TypeError, ValueError):
        return "unknown", "unknown"
    return str(moment.hour), moment.strftime("%A")


def _payment_method(customer: dict[str, Any] | None) -> dict[str, Any]:
    """The customer's primary payment method, as the fixtures store it."""
    if not customer:
        return {}
    methods = (customer.get("metadata") or {}).get("payment_methods")
    if not methods:
        methods = customer.get("payment_methods")
    return dict(methods[0]) if methods else {}


def build_diagnose_prompt(
    case: dict[str, Any],
    customer: dict[str, Any] | None = None,
    event: dict[str, Any] | None = None,
) -> str:
    """Render the diagnose prompt for one case.

    Everything the model may reason from is assembled here, once. A step that
    let the model reach for the case dict itself would have no way to promise
    that the ground-truth fields under ``customer.metadata`` — willingness to
    pay, the counterfactual recovery date — never reach it.
    """
    customer = customer or {}
    metadata = case.get("metadata") or {}
    summary = (
        customer.get("past_events_summary")
        or (customer.get("metadata") or {}).get("past_events_summary")
        or {}
    )
    method = _payment_method(customer)
    hour_ist, day_of_week = _ist_parts(event)

    recovery_days = [
        entry.get("day_of_month")
        for entry in (summary.get("recent_manual_recoveries") or [])
        if entry.get("day_of_month") is not None
    ]
    amount_inr = int(case.get("amount_at_risk_cents") or 0) // 100
    ltv_inr = int(customer.get("ltv_cents") or 0) // 100

    context = f"""\
Context:
  playbook: {case.get("playbook", "unknown")}
  event_type: {(event or {}).get("event_type", "unknown")}
  failure_code: {metadata.get("failure_code") or metadata.get("error_code") or "unknown"}
  failure_reason: {metadata.get("failure_reason") or "unknown"}
  method: {metadata.get("method") or method.get("type") or "unknown"}
  bank: {metadata.get("bank") or method.get("bank") or "unknown"}
  amount_inr: {amount_inr}
  hour_ist: {hour_ist}
  day_of_week: {day_of_week}
  ltv_inr: {ltv_inr}
  tenure_days: {customer.get("tenure_days", "unknown")}
  past_failure_count: {summary.get("recent_failures_on_1st", 0)}
  past_recovery_days_of_month: {recovery_days or "none recorded"}
  bank_success_rate_90d: {method.get("success_rate_90d", "unknown")}
"""

    return f"{_INSTRUCTIONS}\n{_FEW_SHOT}\nNOW DIAGNOSE THIS CASE.\n\n{context}"
