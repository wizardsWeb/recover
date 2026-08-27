"""Pre-compute every Gemini call the demo makes, so the demo makes none.

    poetry run python scripts/warm_llm_cache.py

The free tier allows a dozen requests a minute. A six-scenario walkthrough
issues more than that in bursts, and a rate-limited call falls back to a stub —
which is correct behaviour and a terrible thing to have happen on camera. This
script runs the nine calls ahead of time and leaves them in ``llm_cache``, so
every one during the demo is a database read.

**It warms through the real call paths.** Each target invokes the same function
the agent loop invokes — ``run_diagnose``, ``execute._generate_message``,
``listen._classify`` — rather than rebuilding a prompt that ought to match. The
cache key is a hash of the prompt, so "ought to match" is the only failure that
matters and re-deriving the prompt here is exactly how it would go wrong.

Everything is deterministic because the scenario payloads are pinned:
``_payload_S1`` and friends carry literal timestamps from scenarios.md, and the
diagnose prompt's hour-of-day and day-of-week come from those. The one input
this script cannot know is the merchant's own display name, which lives on the
signed-in user's ``merchants`` row. It defaults to the scenarios.md names and
takes ``--merchant-id`` to read the real row instead — a merchant named
something else produces a different prompt and therefore a live call.

Second run should print nine ticks in under a second with no API calls. That is
the actual check: it proves the keys are stable, not just that Gemini answered.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.agent.playbooks import get_default_action_params
from app.agent.prompts.message_prompt import FALLBACK_MESSAGE
from app.agent.steps.diagnose import run_diagnose
from app.agent.steps.execute import _generate_message
from app.agent.steps.listen import _classify
from app.db import get_service_client
from app.simulator import fixtures
from app.simulator.scenarios import _payload_S1, _payload_S2, _payload_S4

#: The merchant each scenario belongs to, per scenarios.md. Overridden by
#: ``--merchant-id``, which reads the real row instead.
MERCHANTS: dict[str, dict[str, str]] = {
    fixtures.MERCHANT_ZENITH: {"name": "Zenith Learning", "vertical": "edtech_subscription"},
    fixtures.MERCHANT_KAJAL: {"name": "Kajal & Co.", "vertical": "d2c_beauty"},
    fixtures.MERCHANT_SHARMA: {"name": "Sharma Distributors", "vertical": "b2b_distribution"},
}

#: What ``core`` has written to ``recovery_cases.current_step`` by the time a
#: reply is classified: EXECUTE runs immediately before LISTEN, and an injected
#: reply is always picked up on a later pass that re-reads the row.
LISTEN_STEP = "execute"


def as_customer_row(persona: dict[str, Any]) -> dict[str, Any]:
    """Rebuild the ``customers`` row the fixture loader writes for a persona.

    Mirrors ``event_generator.get_or_create_customer`` — including the
    ``is_simulator_fixture`` marker and the lifted ``past_events_summary`` —
    because the prompt builders read that metadata and a shape that differs here
    is a cache key that differs at demo time.
    """
    metadata = dict(persona.get("metadata") or {})
    metadata["is_simulator_fixture"] = True
    if persona.get("past_events_summary"):
        metadata["past_events_summary"] = persona["past_events_summary"]
    return {
        "id": f"warmup_{persona['external_id']}",
        "external_id": persona["external_id"],
        "name": persona.get("name"),
        "phone": persona.get("phone"),
        "email": persona.get("email"),
        "ltv_cents": persona.get("ltv_cents", 0),
        "tenure_days": persona.get("tenure_days", 0),
        "consent": persona.get("consent", {}),
        "metadata": metadata,
    }


def as_case_row(
    persona: dict[str, Any],
    playbook: str,
    amount_at_risk_cents: int,
    payload: dict[str, Any],
    *,
    current_step: str,
) -> dict[str, Any]:
    """Build the enriched case dict ``core._enrich_case`` hands to the steps."""
    return {
        "id": f"warmup_{persona['external_id']}_{playbook}",
        "merchant_id": "warmup",
        "playbook": playbook,
        "amount_at_risk_cents": amount_at_risk_cents,
        "current_step": current_step,
        "metadata": dict(payload),
        "customer_name": persona.get("name"),
        "customer_phone": persona.get("phone"),
        "customer_email": persona.get("email"),
    }


def as_event_row(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": "warmup_event", "event_type": event_type, "payload": dict(payload)}


# ─────────────────────────────────────────────────────────────────────
# The nine targets
# ─────────────────────────────────────────────────────────────────────


def build_targets(
    db: Any,
    merchant_override: dict[str, Any] | None,
) -> list[tuple[str, Callable[[], Awaitable[bool]]]]:
    """Return ``(label, run)`` pairs. Each ``run`` returns True on a real answer."""

    def merchant(slug: str) -> dict[str, Any]:
        return merchant_override or MERCHANTS[slug]

    async def diagnose(
        persona: dict[str, Any],
        playbook: str,
        amount: int,
        payload: dict[str, Any],
        event_type: str,
    ) -> bool:
        case = as_case_row(persona, playbook, amount, payload, current_step="diagnose")
        result = await run_diagnose(
            case,
            playbook,
            db,
            event=as_event_row(event_type, payload),
            customer=as_customer_row(persona),
        )
        # `is_stub` is False only when Gemini actually answered; the fallback
        # path returns the playbook stub untouched.
        return not result.is_stub

    async def message(
        persona: dict[str, Any],
        playbook: str,
        amount: int,
        payload: dict[str, Any],
        arm: str,
        slug: str,
    ) -> bool:
        case = as_case_row(persona, playbook, amount, payload, current_step="execute")
        result = await _generate_message(
            arm,
            case,
            as_customer_row(persona),
            merchant(slug),
            get_default_action_params(playbook, arm),
            db,
        )
        return result is not FALLBACK_MESSAGE

    async def listen(raw: str, playbook: str, amount: int) -> bool:
        case = {
            "playbook": playbook,
            "current_step": LISTEN_STEP,
            "amount_at_risk_cents": amount,
        }
        result = await _classify(raw, None, case, db)
        return not result.is_stub

    return [
        (
            "S1 diagnose — Suresh, ICICI UPI mandate, salary-cycle mismatch",
            lambda: diagnose(
                fixtures.PERSONA_SURESH,
                "subscription_failure",
                299900,
                _payload_S1(),
                "subscription.charged.failed",
            ),
        ),
        (
            "S1 message  — retry_at_inferred_date_plus_whatsapp_fallback, Zenith Learning",
            lambda: message(
                fixtures.PERSONA_SURESH,
                "subscription_failure",
                299900,
                _payload_S1(),
                "retry_at_inferred_date_plus_whatsapp_fallback",
                fixtures.MERCHANT_ZENITH,
            ),
        ),
        (
            "S2 diagnose — Priya, cart abandoned at method selection",
            lambda: diagnose(
                fixtures.PERSONA_PRIYA,
                "checkout_abandonment",
                124000,
                _payload_S2(),
                "checkout.abandoned",
            ),
        ),
        (
            "S2 message  — whatsapp_saved_cart_8pct, Kajal & Co.",
            lambda: message(
                fixtures.PERSONA_PRIYA,
                "checkout_abandonment",
                124000,
                _payload_S2(),
                "whatsapp_saved_cart_8pct",
                fixtures.MERCHANT_KAJAL,
            ),
        ),
        (
            "S4 message  — polite_reminder_whatsapp, Sharma Distributors",
            lambda: message(
                fixtures.PERSONA_MEERA,
                "b2b_overdue",
                14500000,
                _payload_S4(),
                "polite_reminder_whatsapp",
                fixtures.MERCHANT_SHARMA,
            ),
        ),
        (
            'S4 listen   — "boss, 50% abhi kar deti hoon, baaki 25 tak"',
            lambda: listen("boss, 50% abhi kar deti hoon, baaki 25 tak", "b2b_overdue", 14500000),
        ),
        (
            'S5 listen   — "bhaisaab beta ab coaching nahi le raha, cancel kar do please"',
            lambda: listen(
                "bhaisaab beta ab coaching nahi le raha, cancel kar do please",
                "subscription_failure",
                199900,
            ),
        ),
        (
            'S6 listen   — "STOP" (English)',
            lambda: listen("STOP", "failed_payment", 68000),
        ),
        (
            'S6 listen   — "band karo ye messages" (Hinglish)',
            lambda: listen("band karo ye messages", "failed_payment", 68000),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────


def load_merchant(db: Any, merchant_id: str) -> dict[str, Any] | None:
    try:
        resp = db.table("merchants").select("*").eq("id", merchant_id).execute()
    except Exception as exc:  # noqa: BLE001
        print(f"  ! could not read merchant {merchant_id}: {exc}")
        return None
    return dict(resp.data[0]) if resp.data else None


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--merchant-id",
        help=(
            "Warm the message prompts against this merchant's real name and "
            "vertical instead of the scenarios.md defaults."
        ),
    )
    args = parser.parse_args()

    if not os.environ.get("GEMINI_API_KEY"):
        print("✗ GEMINI_API_KEY is not set — every call would return its fallback.")
        print("  Export it (or source the Key Vault secret) and re-run.")
        return 1

    db = get_service_client()

    override = None
    if args.merchant_id:
        override = load_merchant(db, args.merchant_id)
        if override:
            print(f"Merchant: {override.get('name')} ({override.get('vertical')})\n")
        else:
            print(f"Merchant {args.merchant_id} not found — using scenarios.md names.\n")

    targets = build_targets(db, override)
    print(f"Warming {len(targets)} LLM targets…\n")

    failures = 0
    started = time.monotonic()
    for label, run in targets:
        call_started = time.monotonic()
        ok = await run()
        elapsed_ms = int((time.monotonic() - call_started) * 1000)
        print(f"  {'✓' if ok else '✗'} {label}  ({elapsed_ms} ms)")
        failures += 0 if ok else 1

    total_ms = int((time.monotonic() - started) * 1000)
    warmed = len(targets) - failures
    print(f"\n{warmed}/{len(targets)} warmed in {total_ms} ms.")
    if failures:
        print("Re-run to retry the misses — a rate-limited call fails without consuming quota.")
    else:
        print("Re-run to confirm: a fully warm cache completes in well under a second.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
