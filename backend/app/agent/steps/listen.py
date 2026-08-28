"""Step 7 — Listen: what did the customer actually say?

Indian customers reply in Hinglish, in Devanagari, in English, and in all three
inside one sentence. "band karo yeh" and "STOP" mean the same thing and share no
characters, so Gemini classifies — it is the only approach that generalises.

The pattern matcher below is the floor beneath that, not dead code. It runs
whenever the classifier is unavailable, off-schema, or unparseable, because the
one failure mode in this module that is a compliance breach rather than a missed
recovery is a Gemini outage turning "STOP" into "no signal detected". A
classifier that can be down is only safe if something answers when it is.

Matching is word-boundary, not substring. That distinction is load-bearing:
``"by"`` is a promise-to-pay token ("pay by Friday") and a substring of "maybe",
and a naive ``in`` test would read "maybe later" as a commitment and pause the
recovery on it.

Order of evaluation is by consequence, most binding first: an explicit opt-out,
then hardship, then churn, then a bare "cancel", then a promise. A message
carrying two signals resolves to the one that most restricts what the agent may
do next — and the LLM prompt states the same order, so the two layers cannot
disagree about which signal wins. The one deliberate exception is "cancel",
which sits below churn; see the pattern list for why.

The classification is written back onto the ``customer_replies`` row, into
``llm_classification`` and ``applied_state_update``. That second column is also
the "already handled" marker ``core`` filters on when it looks for a pending
reply, so writing it here is what stops a later pass re-applying an opt-out that
has already been honoured.
"""

import re
from datetime import UTC, datetime
from typing import Any

from app.agent.llm import make_gemini_client
from app.agent.models import ListenResult, ReplyIntent
from app.agent.prompts.listen_prompt import (
    FALLBACK_LISTEN,
    LISTEN_SCHEMA,
    build_listen_prompt,
)
from app.logging import get_logger

logger = get_logger(__name__)

#: Phrases that can only mean "stop contacting me". Tested before everything
#: else, because missing one is a compliance breach and honouring one that was
#: not quite meant costs a single recovery.
OPT_OUT_PATTERNS = [
    "stop",
    "band karo",
    "mat bhejo",
    "unsubscribe",
    "opt out",
    "opt-out",
    "band karo yeh",
    "nahi chahiye",
    "do not contact",
]

#: "cancel" on its own, which is genuinely ambiguous.
#:
#: It is the same word in "cancel these messages" and in "cancel my son's
#: coaching", and those need opposite responses: one revokes consent on every
#: channel, the other ends a subscription and hands a high-LTV customer to a
#: retention team. So it is tested *after* the churn phrases — "cancel kar do"
#: reaches CHURN_PATTERNS and is read as churn — and a bare "cancel" with no
#: other signal still falls through to here and revokes, which is the safe
#: reading when there is nothing else to go on.
AMBIGUOUS_OPT_OUT_PATTERNS = ["cancel"]

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
_AMBIGUOUS_OPT_OUT_RE = _compile(AMBIGUOUS_OPT_OUT_PATTERNS)
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
    """Classify the pending customer reply with Gemini, or by pattern if it fails.

    A pass with no reply still returns a ``ListenResult`` — intent ``UNKNOWN``,
    every signal false — rather than ``None``. The timeline's nine steps stay
    nine, and "nobody wrote back" reads as a fact instead of a gap that looks
    like a crash.
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

    raw = str(customer_reply.get("raw_text") or "")
    reply_id = customer_reply.get("id")

    result = await _classify(raw, reply_id, case, supabase_client)
    result.raw_text = raw
    _record_classification(supabase_client, reply_id, result)
    return result


async def _classify(
    raw: str,
    reply_id: Any,
    case: dict[str, Any],
    supabase_client: Any,
) -> ListenResult:
    """Gemini first, pattern matcher second. Never raises."""
    client = make_gemini_client(supabase_client)
    prompt = build_listen_prompt(raw, case)
    payload = await client.generate_structured(prompt, LISTEN_SCHEMA, "listen", FALLBACK_LISTEN)

    # Identity, not equality: `generate_structured` hands back the exact dict it
    # was given on every failure path, so this is the unambiguous "no answer" test.
    if payload is FALLBACK_LISTEN:
        return _pattern_match_fallback(raw, reply_id)

    try:
        return ListenResult(
            reply_id=str(reply_id) if reply_id else None,
            intent=ReplyIntent(payload["intent"]),
            language=str(payload.get("language") or "unknown"),
            opt_out_signal=bool(payload.get("opt_out_signal")),
            hardship_signal=bool(payload.get("hardship_signal")),
            churn_signal=bool(payload.get("churn_signal")),
            extracted_entities=dict(payload.get("extracted_entities") or {}),
            recommended_state_update=payload.get("recommended_state_update"),
            sentiment=payload.get("sentiment"),
            confidence=payload.get("confidence"),
            is_stub=False,
        )
    except Exception as exc:  # noqa: BLE001 - an unreadable classification must not lose the reply
        logger.warning("listen_parse_failed", error=str(exc))
        return _pattern_match_fallback(raw, reply_id)


def _record_classification(
    supabase_client: Any,
    reply_id: Any,
    result: ListenResult,
) -> None:
    """Store the classification on the reply row.

    ``applied_state_update`` doubles as the "already handled" marker, so it is
    never left null on a classified reply — ``NO_ACTION`` is written when the
    classifier recommends nothing, because null would make the next pass pick
    the same reply up again.
    """
    if not reply_id or supabase_client is None:
        return
    try:
        supabase_client.table("customer_replies").update(
            {
                "llm_classification": result.model_dump(mode="json"),
                "applied_state_update": result.recommended_state_update or "NO_ACTION",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", reply_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("listen_classification_write_error", error=str(exc))


def _pattern_match_fallback(raw: str, reply_id: Any = None) -> ListenResult:
    """Classify by keyword when the LLM is unavailable.

    Deliberately blunt and deliberately biased toward stopping. It cannot read
    tone or extract entities, so ``sentiment`` and ``confidence`` stay ``None``
    rather than being invented, and ``is_stub`` stays ``True`` so the UI can say
    which layer answered.
    """
    reply_id_str = str(reply_id) if reply_id else None

    if _matches_any(raw, _OPT_OUT_RE):
        return ListenResult(
            reply_id=reply_id_str,
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
            reply_id=reply_id_str,
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
            reply_id=reply_id_str,
            intent=ReplyIntent.CHURN_CONFIRMATION,
            language="hinglish",
            opt_out_signal=False,
            hardship_signal=False,
            churn_signal=True,
            recommended_state_update="STOP_RECOVERY_HUMAN_RETENTION_HANDOFF",
            is_stub=True,
        )

    if _matches_any(raw, _AMBIGUOUS_OPT_OUT_RE):
        return ListenResult(
            reply_id=reply_id_str,
            intent=ReplyIntent.EXPLICIT_OPT_OUT,
            language="hinglish",
            opt_out_signal=True,
            hardship_signal=False,
            churn_signal=False,
            recommended_state_update="REVOKE_CONSENT_ALL_CHANNELS",
            is_stub=True,
        )

    if _matches_any(raw, _PROMISE_RE):
        return ListenResult(
            reply_id=reply_id_str,
            intent=ReplyIntent.PROMISE_TO_PAY,
            language="hinglish",
            opt_out_signal=False,
            hardship_signal=False,
            churn_signal=False,
            recommended_state_update="PAUSE_RECOVERY_TRACK_PROMISE",
            is_stub=True,
        )

    return ListenResult(
        reply_id=reply_id_str,
        intent=ReplyIntent.NEUTRAL,
        language="unknown",
        opt_out_signal=False,
        hardship_signal=False,
        churn_signal=False,
        is_stub=True,
    )
