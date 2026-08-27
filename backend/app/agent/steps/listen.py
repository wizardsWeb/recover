"""Step 7 — Listen: what did the customer actually say?

Indian customers reply in Hinglish, in Devanagari, in English, and in all three
inside one sentence. "band karo yeh" and "STOP" mean the same thing and share no
characters. Phase 5 hands this to Gemini, which is the only approach that
generalises.

What lives here is the floor beneath that: a pattern matcher over the phrases
the scripted scenarios use. It exists so the loop is testable without an LLM and
so a Gemini outage cannot turn "STOP" into "no signal detected" — the one
failure mode in this module that is a compliance breach rather than a missed
recovery.

Matching is word-boundary, not substring. That distinction is load-bearing:
``"by"`` is a promise-to-pay token ("pay by Friday") and a substring of "maybe",
and a naive ``in`` test would read "maybe later" as a commitment and pause the
recovery on it.

Order of evaluation is by consequence, most binding first: opt-out, then
hardship, then churn, then promise. A message carrying two signals is resolved
in favour of the one that most restricts what the agent may do next.
"""

import re
from typing import Any

from app.agent.models import ListenResult, ReplyIntent

# NOTE: "cancel" appears here and "cancel subscription" under CHURN_PATTERNS.
# Opt-out is tested first, so a bare "cancel" revokes consent rather than
# closing the subscription. That is the safe direction to be wrong in, and
# Phase 5's classifier is what tells the two apart properly.
OPT_OUT_PATTERNS = [
    "stop",
    "band karo",
    "mat bhejo",
    "unsubscribe",
    "opt out",
    "opt-out",
    "cancel",
    "band karo yeh",
    "nahi chahiye",
    "do not contact",
]

PROMISE_TO_PAY_PATTERNS = [
    "kar deta hoon",
    "kar deti hoon",
    "next month",
    "kal pay",
    "by",
    "abhi kar",
    "paisa bhejta",
    "paisa bhejti",
    "will pay",
    "paying soon",
]

HARDSHIP_PATTERNS = [
    "tabiyat",
    "hospital",
    "bimaar",
    "sick",
    "job nahi",
    "naukri gayi",
    "lost job",
    "emergency",
    "accident",
    "death",
    "death in family",
]

CHURN_PATTERNS = [
    "cancel kar do",
    "cancel subscription",
    "band kar do",
    "nahi lena",
    "ab nahi chahiye",
    "no longer needed",
    "not using",
    "not interested",
]


def _compile(patterns: list[str]) -> re.Pattern[str]:
    """Compile a phrase list into one word-boundary alternation."""
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in patterns) + r")\b")


_OPT_OUT_RE = _compile(OPT_OUT_PATTERNS)
_PROMISE_RE = _compile(PROMISE_TO_PAY_PATTERNS)
_HARDSHIP_RE = _compile(HARDSHIP_PATTERNS)
_CHURN_RE = _compile(CHURN_PATTERNS)


def _matches_any(text: str, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.search(text.lower().strip()))


async def run_listen(
    case: dict[str, Any],
    customer_reply: dict[str, Any] | None,
    supabase_client: Any,
) -> ListenResult:
    """Pattern-match the customer reply to classify intent.

    Phase 5 replaces this with Gemini LLM classification that handles Hinglish,
    mixed-language, and edge cases.
    """
    if not customer_reply:
        return ListenResult(
            intent=ReplyIntent.UNKNOWN,
            language="unknown",
            opt_out_signal=False,
            hardship_signal=False,
            churn_signal=False,
            is_stub=True,
        )

    raw = customer_reply.get("raw_text", "")
    reply_id = customer_reply.get("id")

    if _matches_any(raw, _OPT_OUT_RE):
        return ListenResult(
            reply_id=reply_id,
            intent=ReplyIntent.EXPLICIT_OPT_OUT,
            language="hinglish",
            opt_out_signal=True,
            hardship_signal=False,
            churn_signal=False,
            recommended_state_update="REVOKE_CONSENT_ALL_CHANNELS",
            is_stub=True,
        )

    if _matches_any(raw, _HARDSHIP_RE):
        return ListenResult(
            reply_id=reply_id,
            intent=ReplyIntent.HARDSHIP_SIGNAL,
            language="hinglish",
            opt_out_signal=False,
            hardship_signal=True,
            churn_signal=False,
            recommended_state_update="PAUSE_RECOVERY_HUMAN_HANDOFF",
            is_stub=True,
        )

    if _matches_any(raw, _CHURN_RE):
        return ListenResult(
            reply_id=reply_id,
            intent=ReplyIntent.CHURN_CONFIRMATION,
            language="hinglish",
            opt_out_signal=False,
            hardship_signal=False,
            churn_signal=True,
            recommended_state_update="STOP_RECOVERY_HUMAN_RETENTION_HANDOFF",
            is_stub=True,
        )

    if _matches_any(raw, _PROMISE_RE):
        return ListenResult(
            reply_id=reply_id,
            intent=ReplyIntent.PROMISE_TO_PAY,
            language="hinglish",
            opt_out_signal=False,
            hardship_signal=False,
            churn_signal=False,
            recommended_state_update="PAUSE_RECOVERY_TRACK_PROMISE",
            is_stub=True,
        )

    return ListenResult(
        reply_id=reply_id,
        intent=ReplyIntent.NEUTRAL,
        language="unknown",
        opt_out_signal=False,
        hardship_signal=False,
        churn_signal=False,
        is_stub=True,
    )
