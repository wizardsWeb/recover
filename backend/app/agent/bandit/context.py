"""Turning a case into bandit features, and features into a bucket string.

The bandit is *contextual*: an arm that works for a late-night HDFC card failure
is not the arm that works for a 1st-of-month ICICI mandate failure, and a single
posterior per arm would average those into a policy that is wrong for both. The
context bucket is what keeps them apart.

**Bucketing is coarse on purpose.** ``"ICIC:UPI:morning:high"`` throws away far
more than it keeps — the exact minute, the exact rupee amount, the customer's
tenure in days. That is the point. A bandit learns from repetition, and a bucket
fine enough to be unique is a bucket that never gets a second observation. Four
dimensions at this granularity give a demo-scale merchant a few hundred buckets,
most of which will see real traffic.

The full context vector is richer than the bucket and is stored on the decision
row anyway. Nothing reads the extra fields yet; Phase 9's uplift model will, and
capturing them now means the training data exists by the time the model does.

**Ground truth never enters here.** ``customer.metadata`` carries the Phase 9
counterfactual — ``true_willingness_to_pay``, ``would_have_recovered_*`` — and a
bandit that could see those would be cheating at its own benchmark. Every field
this module reads is named explicitly for that reason; there is no ``**metadata``
splat anywhere below.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

#: Fallbacks for the two bucket dimensions that can be genuinely absent. A
#: checkout abandonment has no bank and no method — nothing was attempted — and
#: that absence is itself a stable context worth learning about, so it gets a
#: name rather than being dropped.
UNKNOWN_BANK = "OTHE"
UNKNOWN_METHOD = "OTH"

#: Payment method -> its three-letter bucket code.
_METHOD_CODES: dict[str, str] = {
    "upi": "UPI",
    "card": "CAR",
    "netbanking": "NET",
    "wallet": "WAL",
    "mandate": "MAN",
    "emandate": "MAN",
}

#: LTV band boundaries, in paise. The schema's ``_cents`` columns hold paise, so
#: ₹5,000 is 500_000 — a factor-of-100 error here would put every customer in
#: the top band and collapse the dimension to a constant.
LTV_MED_FLOOR_CENTS = 500_000  # ₹5,000
LTV_HIGH_FLOOR_CENTS = 2_000_000  # ₹20,000

#: Tenure and amount bands. Not part of the bucket string — they ride along in
#: the context vector for Phase 9.
TENURE_ESTABLISHED_DAYS = 180
TENURE_NEW_DAYS = 30
AMOUNT_LARGE_CENTS = 5_000_000  # ₹50,000
AMOUNT_SMALL_CENTS = 100_000  # ₹1,000

#: A customer who has failed on the 1st this many times is showing a pattern,
#: not having a bad month. Two is the smallest number that can be a pattern.
SALARY_MISMATCH_MIN_FAILURES = 2


def _bank_code(raw: Any) -> str:
    """First four characters of the bank name, uppercased.

    Note ``SBI`` yields ``"SBI"`` and not a padded four-character code. The
    bucket is an opaque grouping key — it has to be stable and collision-free,
    not fixed-width — so padding would add a rule without adding a property.
    """
    text = str(raw or "").strip()
    return text[:4].upper() if text else UNKNOWN_BANK


def _method_code(raw: Any) -> str:
    """Three-letter code for a payment method."""
    text = str(raw or "").strip().lower()
    if not text:
        return UNKNOWN_METHOD
    if text in _METHOD_CODES:
        return _METHOD_CODES[text]
    # `upi_autopay`, `card_debit` and friends resolve on their prefix rather
    # than falling to OTH, so a naming variant does not fragment the bucket.
    for name, code in _METHOD_CODES.items():
        if text.startswith(name):
            return code
    return UNKNOWN_METHOD


def _period(hour: int | None) -> str:
    """IST time-of-day band. S3's whole thesis is that night is different."""
    if hour is None:
        return "unknown"
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"  # 21:00-05:59


def _ltv_bucket(ltv_cents: Any) -> str:
    value = int(ltv_cents or 0)
    if value >= LTV_HIGH_FLOOR_CENTS:
        return "high"
    if value >= LTV_MED_FLOOR_CENTS:
        return "med"
    return "low"


def _tenure_bucket(tenure_days: Any) -> str:
    days = int(tenure_days or 0)
    if days >= TENURE_ESTABLISHED_DAYS:
        return "established"
    if days >= TENURE_NEW_DAYS:
        return "returning"
    return "new"


def _amount_bucket(amount_cents: Any) -> str:
    value = int(amount_cents or 0)
    if value >= AMOUNT_LARGE_CENTS:
        return "large"
    if value >= AMOUNT_SMALL_CENTS:
        return "medium"
    return "small"


def _hour_ist(case: dict[str, Any], event: dict[str, Any] | None) -> int | None:
    """The IST hour the triggering thing happened.

    Reads the payload's own timestamp before the row's ``received_at``, because
    a scenario fired today about a payment that failed on Saturday night must
    bucket as Saturday night. Returns ``None`` rather than falling back to the
    wall clock: a bucket that silently means "whenever the pass ran" would let
    one scenario's rewards leak into another's context.
    """
    payload = (event or {}).get("payload") or case.get("metadata") or {}
    stamp = (
        payload.get("attempted_at")
        or payload.get("abandoned_at")
        or (event or {}).get("received_at")
    )
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp)).astimezone(IST).hour
    except (TypeError, ValueError):
        return None


def _resolve_bank(metadata: dict[str, Any], customer: dict[str, Any]) -> Any:
    """Find the bank across the three places an event may name it.

    S1 puts it at ``payload.bank``; S3 puts it inside the ``card`` block as
    ``issuer`` and has no top-level ``bank`` at all. Falling back to the
    customer's stored method keeps a checkout abandonment — which names neither
    — from losing the dimension entirely when the fixture knows it.
    """
    if metadata.get("bank"):
        return metadata["bank"]
    card = metadata.get("card")
    if isinstance(card, dict) and card.get("issuer"):
        return card["issuer"]
    methods = (customer.get("metadata") or {}).get("payment_methods") or customer.get(
        "payment_methods"
    )
    if methods:
        return methods[0].get("bank")
    return None


def extract_context_vector(
    case: dict[str, Any],
    customer: dict[str, Any] | None = None,
    event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the feature dict the bandit conditions on.

    Every field is read by name. Nothing from ``customer.metadata`` reaches the
    output except the two history counters below, which keeps the Phase 9 ground
    truth out of the bandit's reach by construction rather than by discipline.
    """
    customer = customer or {}
    metadata = case.get("metadata") or {}
    summary = (
        (customer.get("metadata") or {}).get("past_events_summary")
        or customer.get("past_events_summary")
        or {}
    )

    hour = _hour_ist(case, event)
    failures_on_first = int(summary.get("recent_failures_on_1st") or 0)

    return {
        "bank": _bank_code(_resolve_bank(metadata, customer)),
        "method": _method_code(metadata.get("method")),
        "hour_ist": hour,
        "period": _period(hour),
        "ltv_bucket": _ltv_bucket(customer.get("ltv_cents")),
        "tenure_bucket": _tenure_bucket(customer.get("tenure_days")),
        "amount_bucket": _amount_bucket(case.get("amount_at_risk_cents")),
        "past_failure_count": failures_on_first,
        # The S1 signal in one boolean: repeated failures on the same day of the
        # month is a timing problem, not a broken instrument.
        "has_salary_mismatch_pattern": failures_on_first >= SALARY_MISMATCH_MIN_FAILURES,
    }


def make_context_bucket(context: dict[str, Any]) -> str:
    """Collapse a context vector to its ``BANK:METHOD:PERIOD:LTV`` grouping key.

    This string is the primary key the posteriors are stored under, so it must
    be a pure function of the four fields and stable across releases. Adding a
    fifth dimension later orphans every posterior learned under the old key —
    which is a migration, not an edit.
    """
    return ":".join(
        [
            str(context.get("bank") or UNKNOWN_BANK),
            str(context.get("method") or UNKNOWN_METHOD),
            str(context.get("period") or "unknown"),
            str(context.get("ltv_bucket") or "low"),
        ]
    )


#: Why each arm suits the context it wins in, in a merchant's words.
#:
#: The bandit's own reason for choosing an arm is "it drew the highest sample",
#: which is true, unfalsifiable, and useless to the person asking why their
#: customer got that message. These sentences are the human-legible half of the
#: same answer; the sampled theta and the full ranking sit beside them on the
#: decision row for anyone who wants the arithmetic.
_ARM_REASONING: dict[str, str] = {
    "retry_at_inferred_date": (
        "Waits for the salary date rather than spending a retry on an empty account"
    ),
    "retry_at_inferred_date_plus_whatsapp_fallback": (
        "Retries when the money is likely to land, with a WhatsApp nudge only if that fails"
    ),
    "immediate_retry": "Retries at once — worth it only when the failure looks transient",
    "silent_retry_next_morning": (
        "Says nothing and retries in the morning, when this bank's success rate recovers"
    ),
    "retry_now": "Retries immediately against a failure believed to be a one-off",
    "retry_at_optimal_hour": "Defers the retry to this bank's best-performing hour",
    "whatsapp_payment_link": "Sends a payment link on the channel this customer actually reads",
    "whatsapp_payment_link_now": (
        "Sends a payment link straight away rather than waiting on a retry"
    ),
    "sms_payment_link": "Falls back to SMS where WhatsApp consent or reach is missing",
    "email_payment_link": "Uses email, the slowest channel, when it is the only one consented",
    "switch_method_upi": "Suggests UPI after a card failure, routing around the failing rail",
    "whatsapp_saved_cart_no_discount": (
        "Reminds without discounting — margin intact where price was not the blocker"
    ),
    "whatsapp_saved_cart_5pct": (
        "A small nudge for a cart that stalled on hesitation rather than price"
    ),
    "whatsapp_saved_cart_8pct": (
        "The discount this cart size and price-sensitivity band responds to"
    ),
    "whatsapp_saved_cart_12pct": (
        "The largest allowed discount — recovers more carts, at a margin this one may not need"
    ),
    "email_saved_cart": "Cart reminder by email, for customers who do not engage on WhatsApp",
    "sms_saved_cart": "Cart reminder by SMS, where it is the only consented channel",
    "suggest_alternate_method": "Offers a different payment rail when the chosen one is failing",
    "polite_reminder_whatsapp": (
        "Opens at the bottom of the tone ladder, as a long relationship deserves"
    ),
    "polite_reminder_email": "A soft first reminder on the formal channel this account uses",
    "firm_reminder_whatsapp": "Raises the tone after a polite reminder went unanswered",
    "firm_reminder_whatsapp_plus_email": (
        "Firm tone across both channels, for an invoice well past its terms"
    ),
    "partial_payment_offer": (
        "Offers to split the invoice, converting a stall into part payment now"
    ),
    "payment_plan_offer": "Structures the balance over time rather than pressing for it at once",
    "accept_promise_to_pay": (
        "Takes the customer at their word and pauses, rather than spending goodwill"
    ),
    "escalate_to_human_ar": "Hands to accounts receivable — past the point automation should push",
    "graduated_b2b_sequence": (
        "Escalates tone step by step over the invoice's life, the pattern this payer responds to"
    ),
    "dunning_email_sequence": (
        "Works a scheduled email sequence — cheap, slow, and the right shape when no "
        "faster channel is consented"
    ),
    "mandate_reregistration": (
        "Asks for a fresh mandate, because the old one can no longer be charged"
    ),
    "pause_with_winback": (
        "Pauses billing and plans a win-back, protecting the relationship over this cycle"
    ),
    "human_handoff": (
        "Puts a person on it — the value at stake is past what automation should decide"
    ),
    "no_op": (
        "Does nothing, because contacting this customer is expected to cost more than it recovers"
    ),
}


def get_arm_reasoning(arm_name: str, context: dict[str, Any]) -> str:
    """One sentence on why this arm fits this context, for the audit trail."""
    base = _ARM_REASONING.get(arm_name, f"Selected '{arm_name}' from this playbook's action space")

    qualifiers: list[str] = []
    if context.get("has_salary_mismatch_pattern"):
        qualifiers.append("repeated failures on the same day of the month")
    if context.get("period") == "night":
        qualifiers.append("a late-night attempt")
    if context.get("ltv_bucket") == "high":
        qualifiers.append("a high-LTV customer")

    if not qualifiers:
        return f"{base}. Context: {make_context_bucket(context)}."
    return f"{base}. Context: {make_context_bucket(context)} — {', '.join(qualifiers)}."
