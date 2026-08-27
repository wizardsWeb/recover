"""Prompt templates for the three LLM-backed steps.

Each module owns three things and nothing else: a Gemini ``responseSchema``, a
``build_*_prompt`` function, and a ``FALLBACK_*`` dict shaped like the schema.
Keeping the prompts out of the step modules is what lets the prompt tests assert
on the rendered string without constructing a Supabase client or an agent loop.
"""

from app.agent.prompts.diagnose_prompt import (
    DIAGNOSE_SCHEMA,
    FALLBACK_DIAGNOSIS,
    ROOT_CAUSES,
    build_diagnose_prompt,
)
from app.agent.prompts.listen_prompt import (
    FALLBACK_LISTEN,
    LISTEN_SCHEMA,
    MAX_REPLY_CHARS,
    STATE_UPDATES,
    build_listen_prompt,
)
from app.agent.prompts.message_prompt import (
    CHANNEL_LIMITS,
    FALLBACK_MESSAGE,
    MESSAGE_SCHEMA,
    TONES,
    build_message_prompt,
)

__all__ = [
    "CHANNEL_LIMITS",
    "DIAGNOSE_SCHEMA",
    "FALLBACK_DIAGNOSIS",
    "FALLBACK_LISTEN",
    "FALLBACK_MESSAGE",
    "LISTEN_SCHEMA",
    "MAX_REPLY_CHARS",
    "MESSAGE_SCHEMA",
    "ROOT_CAUSES",
    "STATE_UPDATES",
    "TONES",
    "build_diagnose_prompt",
    "build_listen_prompt",
    "build_message_prompt",
]
