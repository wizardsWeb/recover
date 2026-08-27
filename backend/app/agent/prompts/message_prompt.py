"""Prompt and schema for step 6 — the customer-facing message.

This is the only prompt in the system whose output a human being reads. That
changes what the guard rails are for. The diagnose prompt is guarded against
inventing evidence an auditor would trust; this one is guarded against inventing
a **number** — a discount that was never approved, an amount that is not owed, a
date nobody agreed to. The bandit decides whether a discount is on the table and
how large; the model's job is to phrase it, never to choose it.

Hinglish is the default register, not a translation target. Indian customers
write and read Latin-script Hindi mixed with English, and a message that
switches to pure formal Hindi reads as a bank notice — which is the one tone
that reliably gets ignored. The three few-shots below are the scenarios.md
messages themselves, so the model is copying a house voice rather than
inventing one.

Length caps are in the prompt *and* re-stated per channel in the rendered
context, because "max 160 chars" is a rule the model follows far more reliably
when it appears next to the channel than when it sits in a list of seven rules.
"""

from typing import Any

#: Registers the message may be written in. Each maps to a real situation:
#: ``warm_hinglish`` for a valued consumer, ``firm_professional`` for a B2B
#: invoice past its second reminder, ``urgent_polite`` for a time-boxed offer.
TONES: list[str] = [
    "warm_hinglish",
    "friendly_english",
    "firm_professional",
    "neutral_reminder",
    "urgent_polite",
]

LANGUAGES: list[str] = ["hinglish", "english", "hindi", "marathi", "tamil"]

#: Per-channel hard limits. WhatsApp's body cap is 1024; SMS is one concatenated
#: segment. Both are enforced in the prompt rather than by truncation, because a
#: message cut mid-sentence is worse than a slightly long one.
CHANNEL_LIMITS: dict[str, int] = {
    "whatsapp": 1024,
    "sms": 160,
    "email": 1024,
}

MESSAGE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "text": {
            "type": "STRING",
            "description": (
                "The message body exactly as the customer will see it, newlines "
                "included. No placeholders other than the payment link given."
            ),
        },
        "cta_text": {
            "type": "STRING",
            "description": "The single call to action, as it appears in the message.",
        },
        "tone": {"type": "STRING", "enum": TONES},
        "language": {"type": "STRING", "enum": LANGUAGES},
        "discount_mentioned": {
            "type": "BOOLEAN",
            "description": (
                "True only if the text names a discount. Must be false when "
                "discount_pct is 0 — this is checked."
            ),
        },
        "generation_reasoning": {
            "type": "STRING",
            "description": "One or two sentences on why this tone and framing suit this customer.",
        },
    },
    "required": [
        "text",
        "cta_text",
        "tone",
        "language",
        "discount_mentioned",
        "generation_reasoning",
    ],
    "propertyOrdering": [
        "text",
        "cta_text",
        "tone",
        "language",
        "discount_mentioned",
        "generation_reasoning",
    ],
}

#: Returned when the LLM is unavailable.
#:
#: Deliberately bland and deliberately amount-free. A fallback that guessed at
#: the amount or the customer's name would be the exact failure this prompt
#: exists to prevent, and it would be indistinguishable from a real generation
#: in the timeline.
FALLBACK_MESSAGE: dict[str, Any] = {
    "text": (
        "Hi, your recent payment could not be completed. "
        "You can complete it here whenever convenient."
    ),
    "cta_text": "Complete payment",
    "tone": "neutral_reminder",
    "language": "english",
    "discount_mentioned": False,
    "generation_reasoning": "LLM unavailable — neutral template used.",
}

#: Three worked examples, one per playbook shape.
#:
#: S2 (Priya) and S4 (Meera) are quoted verbatim from scenarios.md. S1 (Suresh)
#: is *derived*: the script schedules a retry with a contingent WhatsApp
#: fallback but does not print the fallback's copy, so this is written to the
#: scenario's stated tone (`warm_reassuring_hinglish`, no discount, salary-date
#: aware) rather than quoted. Noted here rather than left to look like a quote.
_FEW_SHOTS = """\
EXAMPLE 1 — price-sensitive consumer, approved discount, WhatsApp

Context: merchant Kajal & Co. (d2c_beauty), playbook checkout_abandonment, arm \
whatsapp_saved_cart_8pct, amount_inr 1240, customer Priya, language hinglish, \
ltv_bucket low, tenure_days 90, discount_pct 8, channel whatsapp, \
cart_items "Vitamin C serum, moisturizer, sunscreen"

Output:
{
  "text": "Hi Priya! \\ud83d\\udc95 Aapke cart mein Vitamin C serum + moisturizer \
+ sunscreen wait kar rahe hain \\u2728\\n\\nAaj hi complete karo, aur flat 8% off \
\\u2014 code: PRIYA8\\n\\n\\ud83d\\udc49 [payment link]\\n\\nOffer sirf 24 hours \
ke liye. Miss mat karna!",
  "cta_text": "Complete your order",
  "tone": "warm_hinglish",
  "language": "hinglish",
  "discount_mentioned": true,
  "generation_reasoning": "Warm casual Hinglish suits a young beauty shopper. \
Naming the actual cart items reinforces desire; the 24-hour window creates \
urgency without pressure."
}

EXAMPLE 2 — B2B invoice, no discount, first reminder, WhatsApp

Context: merchant Sharma Distributors (b2b_distribution), playbook b2b_overdue, \
arm polite_reminder_whatsapp, amount_inr 145000, customer Meera, language \
hinglish, ltv_bucket high, tenure_days 2920, discount_pct 0, channel whatsapp, \
cart_items "invoice INV-2026-08847, 60 crates cooking oil, due 20 August, 12 \
days overdue"

Output:
{
  "text": "Hi Meera ji, hope you're well \\ud83d\\ude4f\\n\\nJust a gentle \
reminder \\u2014 invoice INV-2026-08847 (\\u20b91,45,000, 60 crates cooking oil) \
was due 20th August, ab 12 din ho gaye hain.\\n\\nPay karne ke liye ek click: \
[payment link]\\n\\nKoi issue ho toh please batayein, hum help kar sakte hain.",
  "cta_text": "Pay invoice",
  "tone": "neutral_reminder",
  "language": "hinglish",
  "discount_mentioned": false,
  "generation_reasoning": "An 8-year relationship with a chronically late but \
always-paying account earns a soft first reminder. The invoice number and line \
item let her clear it without looking anything up."
}

EXAMPLE 3 — subscription retry fallback, high LTV, no discount, WhatsApp

Context: merchant Zenith Learning (edtech_subscription), playbook \
subscription_failure, arm retry_at_inferred_date_plus_whatsapp_fallback, \
amount_inr 2999, customer Suresh, language hinglish, ltv_bucket high, \
tenure_days 240, discount_pct 0, channel whatsapp, cart_items "Aarav's JEE \
coaching subscription, monthly"

Output:
{
  "text": "Namaste Suresh ji \\ud83d\\ude4f\\n\\nAarav ke JEE coaching ka monthly \
payment (\\u20b92,999) is baar process nahi ho paaya \\u2014 balance ki wajah se \
lagta hai.\\n\\nKoi baat nahi. Jab convenient ho, ek click mein: [payment \
link]\\n\\nAarav ki classes bilkul chalti rahengi. Koi help chahiye toh reply \
kar dijiye.",
  "cta_text": "Complete payment",
  "tone": "warm_hinglish",
  "language": "hinglish",
  "discount_mentioned": false,
  "generation_reasoning": "An 8-month subscriber with a timing problem, not a \
willingness problem. Reassuring that the child's classes continue removes the \
fear that drives churn; no discount is offered because none was approved."
}

END EXAMPLES
"""

_INSTRUCTIONS = """\
You write recovery messages for Indian customers on behalf of a merchant. \
Write ONE message for the customer and context below.

Rules:
1. NEVER invent a number. The amount, the discount percentage and the payment \
link are given to you. Do not add, round, or embellish any of them.
2. If discount_pct is 0, do not mention any discount, offer, or code, and set \
discount_mentioned to false.
3. Exactly ONE call to action. No "or you can also".
4. Respect the channel's character limit stated in the context. SMS has no \
emoji and no line art.
5. Match the customer's preferred_language. Hinglish means Latin-script Hindi \
mixed with English, the way people actually message — not formal Hindi.
6. Use the customer's first name only. Add "ji" for older or B2B customers.
7. Write the payment link exactly as "[payment link]" if no URL is given.
8. Never threaten, never imply legal action, never mention credit scores.
9. Reply with JSON matching the schema. No prose outside the JSON.
"""


def build_message_prompt(
    *,
    merchant_name: str,
    merchant_vertical: str,
    playbook: str,
    arm_name: str,
    amount_inr: int,
    customer_first_name: str,
    preferred_language: str,
    ltv_bucket: str,
    tenure_days: int,
    discount_pct: float,
    channel: str,
    payment_link_url: str,
    cart_items: str,
) -> str:
    """Render the message-generation prompt.

    Keyword-only, because eleven positional strings in a row is a bug waiting to
    swap ``merchant_name`` with ``customer_first_name`` and address a customer
    as their own merchant.
    """
    limit = CHANNEL_LIMITS.get(channel, CHANNEL_LIMITS["whatsapp"])
    emoji_rule = "no emoji (SMS)" if channel == "sms" else "emoji allowed, sparingly"

    context = f"""\
Context:
  merchant_name: {merchant_name}
  merchant_vertical: {merchant_vertical}
  playbook: {playbook}
  arm_name: {arm_name}
  amount_inr: {amount_inr}
  customer_first_name: {customer_first_name}
  preferred_language: {preferred_language}
  ltv_bucket: {ltv_bucket}
  tenure_days: {tenure_days}
  discount_pct: {discount_pct}
  channel: {channel} (hard limit {limit} characters, {emoji_rule})
  payment_link_url: {payment_link_url}
  cart_items: {cart_items}
"""

    return f"{_INSTRUCTIONS}\n{_FEW_SHOTS}\nNOW WRITE THE MESSAGE.\n\n{context}"
