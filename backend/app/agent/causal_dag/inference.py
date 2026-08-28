"""Turning observations into posteriors, and observations out of raw payloads.

Two functions with very different characters. `extract_observed_features` is all
domain trivia — which decline code means what, where in a checkout flow someone
stopped — and it is where this module is most likely to be wrong. `traverse_dag`
is six lines of arithmetic and is where it is least likely to be.

**Three states, not two.** A feature can be True, False, or *absent*, and the
third is not a synonym for the second. "The failure code was not `MANDATE_
REVOKED`" is evidence, and it should push that cause down. "We could not check
whether the bank is degraded" is not evidence about anything, and treating it as
False would quietly rule out an outage every time the network view was
unavailable. Extraction only emits a key it can actually settle.

**Naive Bayes is overconfident and that is worth saying out loud.** The features
inside a playbook are co-symptoms of the same story — a salary-timing failure
produces the 1st-of-month date *and* the insufficient-funds code *and* the
day-4-to-8 recovery — and multiplying their likelihoods as if independent counts
one piece of evidence three times. The ranking that comes out is sound; the
number attached to the winner reads higher than the evidence strictly supports.
It is presented as a confidence, and it should be read as "this explanation fits
much better than the others", not as a calibrated probability.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.agent.causal_dag.definitions import DAG_VERSION, CausalDag, get_dag
from app.logging import get_logger

logger = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")

#: Failures on the 1st before the node by that name fires. Three, to match what
#: the node claims. The bandit's `has_salary_mismatch_pattern` uses two, and the
#: difference is deliberate: that flag feeds an arm choice where being early is
#: cheap, and this one feeds a stated diagnosis where being wrong is not.
FAILURES_ON_FIRST_FOR_PATTERN = 3

#: Days of the month that count as "paid once the salary landed".
MANUAL_RECOVERY_WINDOW = range(4, 9)

#: Seconds on a checkout page before it reads as deliberation, not a misclick.
LONG_SESSION_SECONDS = 180

#: Paise. ₹1,000 — the node's own name.
CART_VALUE_THRESHOLD_PAISE = 100_000

#: IST hours that count as overnight, when bank batch windows run.
NIGHT_START_HOUR = 21
NIGHT_END_HOUR = 6

#: Substrings that identify a decline reason. Matched against the failure code
#: and the human reason together, because gateways put the meaning in whichever
#: of the two they feel like.
_CODE_PATTERNS: dict[str, tuple[str, ...]] = {
    "insufficient_funds_code": ("insufficient", "low_balance", "not_enough"),
    "mandate_revoked_code": ("mandate_revoked", "mandate_cancelled", "revoked", "si_cancelled"),
    "card_expired_code": ("expired", "card_expiry"),
    "authentication_failed_code": ("authentication_failed", "auth_failed", "3ds", "otp_failed"),
    "gateway_timeout_code": ("timeout", "timed_out", "gateway_error", "no_response"),
    "card_blocked_code": ("blocked", "card_blocked", "restricted", "do_not_honor"),
}


def _nested(container: dict[str, Any], key: str) -> dict[str, Any]:
    """A nested dict under `key`, or an empty one. Narrowed for the type checker."""
    value = container.get(key)
    return value if isinstance(value, dict) else {}


def _matches(haystack: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in haystack for pattern in patterns)


def _ist_hour_and_day(stamp: Any) -> tuple[int | None, int | None]:
    """`(hour, day-of-month)` in IST, or `(None, None)` if unreadable.

    IST because both facts are about a person's calendar: a mandate presenting
    on the 1st and a retry landing at midnight are claims about their month and
    their night, and UTC would shift both by five and a half hours.
    """
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None, None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=IST)
    local = parsed.astimezone(IST)
    return local.hour, local.day


def _payload(case: dict[str, Any], event: dict[str, Any] | None) -> dict[str, Any]:
    """The event payload, from whichever of the two carries it.

    Mid-pass `case["metadata"]` *is* the payload; on a re-read of the row it is
    the agent's own working state. Preferring the event when there is one keeps
    the two from diverging.
    """
    if event and isinstance(event.get("payload"), dict):
        return dict(event["payload"])
    metadata = case.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _decline_text(payload: dict[str, Any]) -> str:
    """Every field a decline reason might be hiding in, lowercased and joined.

    `payment.failed` nests its codes under `error`; `subscription.charged.failed`
    puts them at the top level. Reading both means one extractor rather than a
    branch per event type.
    """
    error = _nested(payload, "error")
    parts = [
        payload.get("failure_code"),
        payload.get("failure_reason"),
        error.get("failure_code"),
        error.get("failure_reason"),
        error.get("description"),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def _summary(customer: dict[str, Any] | None) -> dict[str, Any]:
    """`past_events_summary`, wherever the caller keeps it."""
    customer = customer or {}
    metadata = _nested(customer, "metadata")
    summary = metadata.get("past_events_summary") or customer.get("past_events_summary")
    return dict(summary) if isinstance(summary, dict) else {}


# ── Feature extraction ─────────────────────────────────────────────────


def extract_observed_features(
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    event: dict[str, Any] | None,
    playbook: str,
    *,
    network_degraded: bool | None = None,
) -> dict[str, bool]:
    """Read the case into the boolean features its playbook's DAG asks about.

    `network_degraded` is passed in rather than looked up. Whether a bank is
    currently failing across the network is the one fact here that needs a
    database, and keeping the query at the call site is what lets this function
    stay synchronous, pure and trivially testable. Left as None it is omitted
    entirely — see the module docstring on why that is not the same as False.
    """
    payload = _payload(case, event)
    codes = _decline_text(payload)
    summary = _summary(customer)
    features: dict[str, bool] = {}

    if playbook == "subscription_failure":
        _, day = _ist_hour_and_day(payload.get("attempted_at"))
        features["payment_failed"] = True
        for node_id in (
            "insufficient_funds_code",
            "mandate_revoked_code",
            "card_expired_code",
        ):
            features[node_id] = _matches(codes, _CODE_PATTERNS[node_id])
        if day is not None:
            features["failure_on_1st_dom"] = day == 1
        features["failure_on_1st_for_3_months"] = (
            int(summary.get("recent_failures_on_1st") or 0) >= FAILURES_ON_FIRST_FOR_PATTERN
        )
        recoveries = summary.get("recent_manual_recoveries")
        if isinstance(recoveries, list):
            features["manual_recovery_on_day_4_to_8"] = any(
                int((entry or {}).get("day_of_month") or 0) in MANUAL_RECOVERY_WINDOW
                for entry in recoveries
                if isinstance(entry, dict)
            )

    elif playbook == "failed_payment":
        error = _nested(payload, "error")
        hour, _ = _ist_hour_and_day(error.get("attempted_at") or payload.get("attempted_at"))
        features["payment_failed"] = True
        for node_id in (
            "insufficient_funds_code",
            "card_expired_code",
            "authentication_failed_code",
            "gateway_timeout_code",
            "card_blocked_code",
        ):
            features[node_id] = _matches(codes, _CODE_PATTERNS[node_id])
        features["upi_method"] = str(payload.get("method") or "").lower().startswith("upi")
        if hour is not None:
            features["night_hour_attempt"] = hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR

    elif playbook == "checkout_abandonment":
        stage = str(payload.get("dropoff_stage") or "").lower()
        if stage:
            features["dropped_at_method_select"] = "method" in stage
            features["dropped_at_otp"] = "otp" in stage
            features["dropped_at_3ds"] = "3ds" in stage or "secure" in stage
        duration = payload.get("session_duration_seconds")
        if duration is not None:
            features["high_session_duration"] = int(duration) >= LONG_SESSION_SECONDS
        cart_value = payload.get("cart_value")
        if cart_value is not None:
            features["cart_value_above_1000"] = int(cart_value) >= CART_VALUE_THRESHOLD_PAISE
        if summary:
            features["returning_customer"] = int(summary.get("total_charges") or 0) > 1
            features["first_time_abandonment"] = int(summary.get("recent_abandonments") or 0) == 0

    elif playbook == "b2b_overdue":
        days_overdue = payload.get("days_overdue")
        if days_overdue is not None:
            features["days_overdue_above_30"] = int(days_overdue) > 30
            features["days_overdue_above_60"] = int(days_overdue) > 60
        if summary:
            features["always_paid_eventually"] = bool(summary.get("always_paid_eventually"))
            features["first_time_late"] = int(summary.get("previous_late_invoices") or 0) == 0
        for node_id, key in (
            ("invoice_disputed_flag", "disputed"),
            ("partial_payment_made", "partial_payment_cents"),
            ("no_response_to_reminders", "reminders_unanswered"),
        ):
            if key in payload:
                features[node_id] = bool(payload[key])

    # Only ever added when the caller actually established it.
    if network_degraded is not None:
        features["bank_downtime_signal"] = network_degraded

    dag = get_dag(playbook)
    if dag is None:
        return features

    # A feature the graph has no node for cannot influence a posterior, and
    # silently carrying it would let a typo look like evidence that was
    # considered and found irrelevant.
    known = {node.node_id for node in dag.observables}
    unknown = set(features) - known
    if unknown:
        logger.warning("dag_unknown_features", playbook=playbook, features=sorted(unknown))
    return {node_id: value for node_id, value in features.items() if node_id in known}


# ── Inference ──────────────────────────────────────────────────────────


def _causal_path(dag: CausalDag, observed: dict[str, bool], root_cause: str) -> list[str]:
    """The chain the diagram animates: what was seen, then what explains it.

    Only observables that fired, in the graph's own declaration order, and only
    ones the winning cause actually accounts for — an unrelated True symptom in
    the path would read as supporting a conclusion it had no part in. The cause
    goes last, so the path reads left to right as evidence into explanation.
    """
    supporting = [
        node.node_id
        for node in dag.observables
        if observed.get(node.node_id)
        and dag.likelihood(root_cause, node.node_id) >= (node.base_rate or 0.5)
    ]
    return [*supporting, root_cause]


def traverse_dag(playbook: str, observed_features: dict[str, bool]) -> dict[str, Any]:
    """Posterior over root causes, given what was observed.

    Synchronous, allocation-light and free of I/O — it runs on every case, and a
    diagnosis that needed a network round trip would be one more thing between a
    failed payment and a retry.

    Plain products rather than log-space. Ten features at likelihoods no lower
    than 0.01 bottom out around 1e-20, which float64 holds comfortably; the
    logarithm would be the right call on a graph an order of magnitude bigger,
    and the wrong kind of clever on this one.
    """
    dag = get_dag(playbook)
    if dag is None:
        logger.warning("dag_missing", playbook=playbook)
        return {
            "root_cause": "unknown",
            "posterior_probability": 0.0,
            "causal_path": [],
            "alternative_hypotheses": [],
            "observed_features_used": [],
            "posteriors": {},
            "dag_version": DAG_VERSION,
            "dag_available": False,
        }

    observed = {
        node_id: bool(value)
        for node_id, value in observed_features.items()
        if dag.node(node_id) is not None
    }

    scores: dict[str, float] = {}
    for cause in dag.root_causes:
        score = cause.prior_probability or 0.0
        for node_id, seen in observed.items():
            likelihood = dag.likelihood(cause.node_id, node_id)
            score *= likelihood if seen else (1.0 - likelihood)
        scores[cause.node_id] = score

    total = sum(scores.values())
    if total <= 0.0:
        # Every cause was ruled out — a combination of evidence the table says
        # is impossible, which means the table is wrong rather than the case.
        # Falling back to the priors keeps a diagnosis available and says so.
        logger.warning("dag_impossible_evidence", playbook=playbook, observed=observed)
        posteriors = {
            cause.node_id: round(cause.prior_probability or 0.0, 4) for cause in dag.root_causes
        }
    else:
        posteriors = {node_id: round(score / total, 4) for node_id, score in scores.items()}

    ranked = sorted(posteriors.items(), key=lambda item: item[1], reverse=True)
    root_cause, probability = ranked[0]

    return {
        "root_cause": root_cause,
        "posterior_probability": probability,
        "causal_path": _causal_path(dag, observed, root_cause),
        "alternative_hypotheses": [
            {"cause": node_id, "probability": value} for node_id, value in ranked[1:4]
        ],
        "observed_features_used": sorted(node_id for node_id, seen in observed.items() if seen),
        "posteriors": posteriors,
        "dag_version": DAG_VERSION,
        "dag_available": True,
    }
