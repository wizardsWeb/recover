"""What the prompts must contain, and what the fallback matcher must catch.

Two different things are under test here and they are tested for two different
reasons.

The prompt assertions are cheap regression guards on *facts reaching the model*.
A refactor that drops the bank from the diagnose context, or the merchant from
the message context, produces a prompt that still renders, still parses, and
quietly reasons about nothing — the failure is invisible without an assertion
that the value is in the string.

The ``_pattern_match_fallback`` assertions are the compliance floor. When Gemini
is down, this function is the only thing standing between "STOP" and a message
the customer explicitly refused. It is tested here rather than through the loop
because it must hold whatever the loop is doing.
"""

from app.agent.prompts import (
    MAX_REPLY_CHARS,
    build_diagnose_prompt,
    build_listen_prompt,
    build_message_prompt,
)
from app.agent.steps.listen import _pattern_match_fallback

CASE = {
    "playbook": "subscription_failure",
    "current_step": "execute",
    "amount_at_risk_cents": 299900,
    "metadata": {
        "bank": "ICICI",
        "method": "upi",
        "failure_code": "BAD_REQUEST_ERROR",
        "failure_reason": "insufficient_funds",
        "attempted_at": "2026-09-01T10:32:14+05:30",
    },
}

CUSTOMER = {
    "name": "Suresh Iyer",
    "ltv_cents": 2700000,
    "tenure_days": 240,
    "metadata": {
        "preferred_language": "hinglish",
        "past_events_summary": {
            "recent_failures_on_1st": 3,
            "recent_manual_recoveries": [{"day_of_month": 7}, {"day_of_month": 4}],
        },
    },
}

EVENT = {"event_type": "subscription.charged.failed", "payload": CASE["metadata"]}


# ── diagnose ───────────────────────────────────────────────────────────


def test_build_diagnose_prompt_carries_the_case_facts() -> None:
    prompt = build_diagnose_prompt(CASE, CUSTOMER, EVENT)

    assert prompt
    assert "ICICI" in prompt
    assert "insufficient_funds" in prompt
    assert "subscription.charged.failed" in prompt
    # Money reaches the model in rupees, not paise: 299900 paise is Rs 2,999,
    # and a model told "299900" reasons about a different customer entirely.
    assert "amount_inr: 2999" in prompt
    assert "ltv_inr: 27000" in prompt


def test_build_diagnose_prompt_derives_ist_hour_and_weekday() -> None:
    """S3 turns on a Saturday 11:34pm failure, so these two fields must be real."""
    prompt = build_diagnose_prompt(CASE, CUSTOMER, EVENT)

    assert "hour_ist: 10" in prompt
    assert "day_of_week: Tuesday" in prompt


def test_build_diagnose_prompt_says_unknown_rather_than_guessing() -> None:
    """A missing timestamp must not silently become the time the pass ran."""
    prompt = build_diagnose_prompt({"playbook": "failed_payment"}, None, None)

    assert "hour_ist: unknown" in prompt
    assert "day_of_week: unknown" in prompt
    assert "bank: unknown" in prompt


# ── listen ─────────────────────────────────────────────────────────────


def test_build_listen_prompt_contains_the_reply() -> None:
    prompt = build_listen_prompt("band karo ye messages", CASE)

    assert "band karo ye messages" in prompt
    assert "subscription_failure" in prompt


def test_build_listen_prompt_truncates_a_long_reply() -> None:
    reply = "a" * 900
    prompt = build_listen_prompt(reply, CASE)

    assert "a" * MAX_REPLY_CHARS in prompt
    assert "a" * (MAX_REPLY_CHARS + 1) not in prompt


# ── message ────────────────────────────────────────────────────────────


def _message_prompt(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "merchant_name": "Kajal & Co.",
        "merchant_vertical": "d2c_beauty",
        "playbook": "checkout_abandonment",
        "arm_name": "whatsapp_saved_cart_8pct",
        "amount_inr": 1240,
        "customer_first_name": "Priya",
        "preferred_language": "hinglish",
        "ltv_bucket": "low",
        "tenure_days": 90,
        "discount_pct": 8,
        "channel": "whatsapp",
        "payment_link_url": "[payment link]",
        "cart_items": "Vitamin C serum, Hydra moisturizer",
    }
    kwargs.update(overrides)
    return build_message_prompt(**kwargs)  # type: ignore[arg-type]


def test_build_message_prompt_contains_the_merchant_and_the_customer() -> None:
    prompt = _message_prompt()

    assert "Kajal & Co." in prompt
    assert "Priya" in prompt
    assert "Vitamin C serum" in prompt
    assert "discount_pct: 8" in prompt


def test_build_message_prompt_states_the_channel_limit() -> None:
    """The cap sits next to the channel, where the model reliably reads it."""
    assert "hard limit 160 characters" in _message_prompt(channel="sms")
    assert "no emoji (SMS)" in _message_prompt(channel="sms")
    assert "hard limit 1024 characters" in _message_prompt(channel="whatsapp")


# ── the compliance floor ───────────────────────────────────────────────


def test_pattern_fallback_catches_english_stop() -> None:
    result = _pattern_match_fallback("STOP")

    assert result.opt_out_signal is True
    assert result.intent == "explicit_opt_out"
    assert result.recommended_state_update == "REVOKE_CONSENT_ALL_CHANNELS"
    # The keyword matcher answered, not the model.
    assert result.is_stub is True


def test_pattern_fallback_catches_hinglish_opt_out() -> None:
    assert _pattern_match_fallback("band karo ye messages").opt_out_signal is True


def test_pattern_fallback_catches_hardship() -> None:
    result = _pattern_match_fallback("papa ki tabiyat kharab hai")

    assert result.hardship_signal is True
    assert result.opt_out_signal is False
    assert result.recommended_state_update == "PAUSE_RECOVERY_HUMAN_HANDOFF"


def test_pattern_fallback_does_not_read_maybe_as_a_promise() -> None:
    """ "by" is a promise token and a substring of "maybe" — matching is word-boundary."""
    result = _pattern_match_fallback("maybe later")

    assert result.intent == "neutral"


def test_pattern_fallback_carries_the_reply_id_through() -> None:
    assert _pattern_match_fallback("STOP", "reply-123").reply_id == "reply-123"
