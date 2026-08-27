"""Context extraction and bucketing.

The bucket string is the primary key every posterior is stored under, so the
properties worth testing are the ones that would silently corrupt the bandit's
memory rather than crash it:

* **Stability.** The same case must produce the same bucket on every pass, or a
  reward lands in a bucket the decision never came from and the arm is credited
  for someone else's outcome.
* **Separation.** Two contexts the bandit is meant to distinguish must not
  collapse into one key. That is the entire value of a *contextual* bandit — a
  bucket that ignores the bank averages HDFC's behaviour with ICICI's.
* **Honest absence.** A checkout abandonment has no bank and no method, and a
  timestamp can be missing. Those must resolve to named, stable values, never to
  the wall clock — a bucket meaning "whenever the pass ran" is one that leaks
  every scenario's rewards into every other.
"""

from typing import Any

from app.agent.bandit.context import (
    extract_context_vector,
    get_arm_reasoning,
    make_context_bucket,
)
from app.simulator import fixtures
from app.simulator.scenarios import _payload_S1, _payload_S2, _payload_S3


def as_customer(persona: dict[str, Any]) -> dict[str, Any]:
    """The ``customers`` row shape the loop hands the bandit."""
    metadata = dict(persona.get("metadata") or {})
    metadata["past_events_summary"] = persona.get("past_events_summary")
    return {
        "ltv_cents": persona.get("ltv_cents", 0),
        "tenure_days": persona.get("tenure_days", 0),
        "metadata": metadata,
    }


def bucket_for(persona: dict[str, Any], payload: dict[str, Any], amount: int) -> str:
    case = {"metadata": payload, "amount_at_risk_cents": amount}
    context = extract_context_vector(case, as_customer(persona), {"payload": payload})
    return make_context_bucket(context)


def test_the_same_case_always_buckets_the_same_way() -> None:
    """Stability is the property the whole reward path depends on."""
    first = bucket_for(fixtures.PERSONA_SURESH, _payload_S1(), 299900)
    second = bucket_for(fixtures.PERSONA_SURESH, _payload_S1(), 299900)

    assert first == second


def test_suresh_buckets_as_icici_upi_morning_high_ltv() -> None:
    """S1's context, spelled out: 10:32 IST on ICICI UPI, a Rs 27,000 subscriber."""
    assert bucket_for(fixtures.PERSONA_SURESH, _payload_S1(), 299900) == "ICIC:UPI:morning:high"


def test_a_different_bank_is_a_different_bucket() -> None:
    """Otherwise the bandit averages two banks' behaviour into one policy."""
    payload = dict(_payload_S1())
    payload["bank"] = "HDFC"

    assert bucket_for(fixtures.PERSONA_SURESH, payload, 299900) == "HDFC:UPI:morning:high"


def test_a_different_hour_is_a_different_bucket() -> None:
    """S3's thesis is that a late-night failure is not a morning failure."""
    payload = dict(_payload_S1())
    payload["attempted_at"] = "2026-09-01T23:32:14+05:30"

    assert bucket_for(fixtures.PERSONA_SURESH, payload, 299900) == "ICIC:UPI:night:high"


def test_a_checkout_with_no_bank_or_method_gets_named_fallbacks() -> None:
    """Nothing was attempted, so there is no rail to name — and that is stable."""
    bucket = bucket_for(fixtures.PERSONA_PRIYA, _payload_S2(), 124000)

    assert bucket.startswith("OTHE:OTH:")
    assert bucket == "OTHE:OTH:evening:low"


def test_a_card_issuer_is_found_inside_the_card_block() -> None:
    """S3 has no top-level ``bank`` — the issuer lives under ``card``."""
    assert bucket_for(fixtures.PERSONA_ADITYA, _payload_S3(), 84000) == "HDFC:CAR:night:low"


def test_a_missing_timestamp_is_unknown_not_now() -> None:
    """Falling back to the wall clock would make the bucket drift by run time."""
    context = extract_context_vector(
        {"metadata": {"bank": "AXIS", "method": "netbanking"}}, {}, None
    )

    assert context["hour_ist"] is None
    assert context["period"] == "unknown"
    assert make_context_bucket(context) == "AXIS:NET:unknown:low"


def test_ltv_bands_are_read_in_paise() -> None:
    """The columns hold paise; a factor-of-100 slip would band everyone 'high'."""
    low = extract_context_vector({}, {"ltv_cents": 58_000}, None)  # Rs 580
    med = extract_context_vector({}, {"ltv_cents": 900_000}, None)  # Rs 9,000
    high = extract_context_vector({}, {"ltv_cents": 2_700_000}, None)  # Rs 27,000

    assert (low["ltv_bucket"], med["ltv_bucket"], high["ltv_bucket"]) == ("low", "med", "high")


def test_the_salary_mismatch_flag_needs_a_pattern_not_a_bad_month() -> None:
    def flag(failures: int) -> bool:
        customer = {"metadata": {"past_events_summary": {"recent_failures_on_1st": failures}}}
        return bool(extract_context_vector({}, customer, None)["has_salary_mismatch_pattern"])

    assert flag(0) is False
    assert flag(1) is False
    assert flag(2) is True
    assert flag(3) is True


def test_the_ground_truth_never_reaches_the_context() -> None:
    """Phase 9's counterfactual is what the bandit is scored against.

    If ``true_willingness_to_pay`` leaked into the features the bandit conditions
    on, every uplift measurement built on it would be circular.
    """
    context = extract_context_vector({}, as_customer(fixtures.PERSONA_SURESH), None)

    leaked = {
        "true_willingness_to_pay",
        "would_have_recovered_without_intervention",
        "would_have_recovered_by_days",
        "churn_intent",
        "opts_out_on_contact",
    }
    assert leaked.isdisjoint(context.keys())


def test_arm_reasoning_names_the_arm_and_the_context() -> None:
    context = extract_context_vector(
        {"metadata": _payload_S1(), "amount_at_risk_cents": 299900},
        as_customer(fixtures.PERSONA_SURESH),
        {"payload": _payload_S1()},
    )
    reasoning = get_arm_reasoning("retry_at_inferred_date_plus_whatsapp_fallback", context)

    assert "money is likely to land" in reasoning
    assert "ICIC:UPI:morning:high" in reasoning
    # Suresh's three 1st-of-month failures and his LTV both qualify the sentence.
    assert "same day of the month" in reasoning
    assert "high-LTV" in reasoning


def test_an_unknown_arm_still_gets_a_sentence() -> None:
    """A new arm must not produce a KeyError three frames into the audit write."""
    assert "not_a_real_arm" in get_arm_reasoning("not_a_real_arm", {})
