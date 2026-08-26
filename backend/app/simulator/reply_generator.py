"""Canonical customer replies with known intent labels.

Phase 2 does not classify anything — the LLM classifier lands in Phase 5. What
this module gives us now is a *labelled* corpus: each example carries the intent
the classifier is expected to return, so Phase 5 can be scored against it rather
than eyeballed.

The replies are deliberately messy. Real Indian customer replies are Hinglish in
Latin script, unpunctuated, and often carry the decisive signal in a single word
("STOP", "band karo", "cancel"). A classifier tuned on clean English will miss
every one of them, and the simulator exists to make that failure visible before
a customer does.

Intent surface (the labels Phase 5 must produce):

``explicit_opt_out``
    Hard compliance stop. Revoke consent, halt everything in flight.
``promise_to_pay``
    A commitment with a date and sometimes an amount. Pause pressure, set a
    follow-up for the promised date.
``soft_promise``
    Vague intent, no date. Worth one gentle follow-up, not a sequence.
``churn_confirmation``
    They are leaving. Stop recovery, hand to a human before auto-cancelling.
``hardship_signal``
    Genuine inability to pay. Back off, offer flexibility, never escalate.
``dispute``
    They contest the amount or the goods. Route to a human; retrying is wrong.
``payment_already_made``
    Reconciliation gap on our side, not theirs. Stop immediately and verify.
``confusion``
    They do not know what this is. Clarify before asking again.
``question``
    A real question that needs an answer before payment can happen.
"""

import random
from typing import Any

REPLY_EXAMPLES: list[dict[str, Any]] = [
    {
        "text": "STOP",
        "expected_intent": "explicit_opt_out",
        "language": "english",
    },
    {
        "text": "band karo ye messages",
        "expected_intent": "explicit_opt_out",
        "language": "hinglish",
    },
    {
        "text": "mujhe koi message mat bhejo, unsubscribe",
        "expected_intent": "explicit_opt_out",
        "language": "hinglish",
    },
    {
        "text": "boss, 50% abhi kar deti hoon, baaki 25 tak",
        "expected_intent": "promise_to_pay",
        "language": "hinglish",
        "expected_entities": {"partial_pct": 50, "promise_date_hint": "25th"},
    },
    {
        "text": "salary 7 tarikh ko aati hai, uske baad pakka pay kar dunga",
        "expected_intent": "promise_to_pay",
        "language": "hinglish",
        "expected_entities": {"promise_date_hint": "7th", "reason": "salary_cycle"},
    },
    {
        "text": "cheque ready hai, Monday ko courier kar denge",
        "expected_intent": "promise_to_pay",
        "language": "hinglish",
        "expected_entities": {"promise_date_hint": "monday", "method": "cheque"},
    },
    {
        "text": "bhaisaab beta ab coaching nahi le raha, cancel kar do please",
        "expected_intent": "churn_confirmation",
        "language": "hinglish",
    },
    {
        "text": "we've moved to another vendor, please close the account",
        "expected_intent": "churn_confirmation",
        "language": "english",
    },
    {
        "text": "papa ki tabiyat kharab hai, next month kar dunga",
        "expected_intent": "hardship_signal",
        "language": "hinglish",
        "expected_entities": {"reason": "family_medical", "promise_date_hint": "next_month"},
    },
    {
        "text": "job chali gayi hai yaar, thoda time do",
        "expected_intent": "hardship_signal",
        "language": "hinglish",
        "expected_entities": {"reason": "job_loss"},
    },
    {
        "text": "kal try karta hoon",
        "expected_intent": "soft_promise",
        "language": "hinglish",
    },
    {
        "text": "dekhta hoon",
        "expected_intent": "soft_promise",
        "language": "hinglish",
    },
    {
        "text": "ye amount galat hai, humne toh 40 crate hi liye the",
        "expected_intent": "dispute",
        "language": "hinglish",
        "expected_entities": {"disputed_quantity": 40},
    },
    {
        "text": "goods damaged aaye the, credit note pending hai aapke side se",
        "expected_intent": "dispute",
        "language": "hinglish",
        "expected_entities": {"reason": "damaged_goods"},
    },
    {
        "text": "payment already ho gaya hai bhai, UTR bhej raha hoon",
        "expected_intent": "payment_already_made",
        "language": "hinglish",
        "expected_entities": {"proof_type": "utr"},
    },
    {
        "text": "ye kis cheez ka message hai? maine kuch order nahi kiya",
        "expected_intent": "confusion",
        "language": "hinglish",
    },
    {
        "text": "UPI se ho jayega ya card hi chahiye?",
        "expected_intent": "question",
        "language": "hinglish",
        "expected_entities": {"topic": "payment_method"},
    },
    {
        "text": "can I pay half now and half after Diwali?",
        "expected_intent": "question",
        "language": "english",
        "expected_entities": {"topic": "payment_plan"},
    },
]

#: Every intent label present in the corpus, in first-seen order.
INTENTS: list[str] = list(dict.fromkeys(example["expected_intent"] for example in REPLY_EXAMPLES))


def get_random_example(intent: str | None = None) -> dict[str, Any]:
    """Return one example, optionally restricted to a single intent.

    Powers the reply injector's rotating placeholder and its "insert example"
    link. Raises rather than returning ``None`` for an unknown intent — a typo
    in a label should fail loudly, not silently hand back the wrong corpus.
    """
    if intent is None:
        return random.choice(REPLY_EXAMPLES)

    matches = [example for example in REPLY_EXAMPLES if example["expected_intent"] == intent]
    if not matches:
        raise ValueError(f"No reply examples for intent {intent!r}. Known: {', '.join(INTENTS)}")
    return random.choice(matches)
