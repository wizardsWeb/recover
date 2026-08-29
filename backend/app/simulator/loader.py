"""Loading, inspecting, and tearing down the demo fixture set.

The three functions here are the simulator's lifecycle. All of them run through
the caller's Supabase client, so RLS — not a ``WHERE merchant_id = ...`` we
remembered to write — is what keeps one merchant's demo out of another's.

Two decisions worth stating:

**Past history is stored on the customer, not as events.** Suresh's three prior
failed-then-recovered months are context for the diagnosis, not events Recover
observed. Writing them to ``events`` would mean the case list and the event
stream both open with rows that never came from a webhook, and every later count
("events this week") would be wrong. They live in ``customers.metadata``.

**Reset deletes only what the simulator made.** Every fixture customer is
stamped ``metadata.is_simulator_fixture = true`` and reset keys off that stamp,
so a merchant who added their own customer alongside the demo keeps it.
"""

import asyncio
from typing import Any

from app.agent.bandit.context import extract_context_vector, make_context_bucket
from app.agent.bandit.thompson import write_posterior
from app.agent.causal_dag.seed import seed_causal_dag
from app.db import get_service_client
from app.logging import get_logger
from app.simulator import fixtures
from app.simulator.event_generator import get_or_create_customer
from app.simulator.scenarios import (
    _payload_S1,
    _payload_S2,
    _payload_S3,
    _payload_S4,
    _payload_S5,
    _payload_S6,
)

log = get_logger(__name__)

#: Every persona the simulator manages: the six scripted ones plus the eight
#: synthetic customers B3's outage burst needs.
_MANAGED_PERSONAS: list[dict[str, Any]] = [
    *fixtures.ALL_PERSONAS,
    *fixtures.B3_SYNTHETIC_CUSTOMERS,
]


def _replace_payment_methods(
    supabase_client: Any, customer_id: str, methods: list[dict[str, Any]]
) -> int:
    """Delete and reinsert this customer's payment methods.

    Delete-then-insert rather than a diff: there are at most two rows per
    customer, they carry no foreign keys pointing *at* them yet, and a diff
    would be more code defending against a case that cannot arise at this
    scale. Revisit if Phase 7 starts linking execution attempts to a method row.
    """
    supabase_client.table("payment_methods").delete().eq("customer_id", customer_id).execute()
    if not methods:
        return 0

    rows = [
        {
            "customer_id": customer_id,
            "type": method["type"],
            "bin": method.get("bin"),
            "bank": method.get("bank"),
            "success_rate_90d": method.get("success_rate_90d"),
            "metadata": method.get("metadata", {}),
        }
        for method in methods
    ]
    result = supabase_client.table("payment_methods").insert(rows).execute()
    return len(result.data or [])


async def load_fixtures_for_merchant(
    supabase_client: Any, merchant_id: str, trace_id: str
) -> dict[str, Any]:
    """Upsert every persona, their payment methods, and their history summary.

    Idempotent: running it twice leaves six personas and eight payment methods,
    not twelve and sixteen. The customer row is reused; the payment methods and
    the history summary are rewritten, so editing a fixture in
    ``fixtures.py`` and reloading actually takes effect.
    """
    customers_created = 0
    payment_methods = 0

    for persona in _MANAGED_PERSONAS:
        before = (
            supabase_client.table("customers")
            .select("id")
            .eq("merchant_id", merchant_id)
            .eq("external_id", persona["external_id"])
            .limit(1)
            .execute()
        )
        customer = get_or_create_customer(supabase_client, merchant_id, persona)
        if not before.data:
            customers_created += 1
        else:
            # Existing row: refresh the fields a fixture edit would change, so a
            # reload is a real reload rather than a no-op.
            metadata = dict(persona.get("metadata") or {})
            metadata["is_simulator_fixture"] = True
            if persona.get("past_events_summary"):
                metadata["past_events_summary"] = persona["past_events_summary"]
            supabase_client.table("customers").update(
                {
                    "name": persona.get("name"),
                    "phone": persona.get("phone"),
                    "email": persona.get("email"),
                    "ltv_cents": persona.get("ltv_cents", 0),
                    "tenure_days": persona.get("tenure_days", 0),
                    "consent": persona.get("consent", {}),
                    "metadata": metadata,
                }
            ).eq("id", customer["id"]).execute()

        payment_methods += _replace_payment_methods(
            supabase_client, customer["id"], persona.get("payment_methods", [])
        )

    # Seeded last, and after the customers exist: the bucket for each scenario
    # is derived from that persona's own LTV and payment method, so the priors
    # are only meaningful alongside the personas they describe.
    priors = await seed_bandit_priors(supabase_client, merchant_id)

    # The causal graph is global reference data, not this merchant's, so it is
    # published rather than seeded per tenant — running it here just means a
    # freshly loaded environment has the table populated without a second call.
    # Failure is swallowed: the agent reasons from `definitions.py`, so an
    # unwritten table costs a SQL view of the graph and nothing else.
    dag_nodes = 0
    try:
        # The service-role client, not the caller's. `causal_dag` has no
        # merchant column, so its RLS grants an authenticated user SELECT and
        # nothing else — writing it through the request's own client fails with
        # 42501, which is the mistake Phase 10's downtime endpoint made.
        dag_nodes = int((await asyncio.to_thread(seed_causal_dag, get_service_client()))["nodes"])
    except Exception as exc:  # noqa: BLE001
        log.warning("causal_dag_seed_failed", error=str(exc))

    supabase_client.table("audit_events").insert(
        {
            "case_id": None,
            "merchant_id": merchant_id,
            "actor": "system",
            "event": "fixtures_loaded",
            "details": {
                "customers": len(_MANAGED_PERSONAS),
                "customers_created": customers_created,
                "payment_methods": payment_methods,
                "bandit_priors": priors,
                "causal_dag_nodes": dag_nodes,
            },
            "trace_id": trace_id,
        }
    ).execute()

    log.info(
        "simulator.fixtures_loaded",
        merchant_id=merchant_id,
        customers=len(_MANAGED_PERSONAS),
        customers_created=customers_created,
        payment_methods=payment_methods,
    )
    return {
        "customers": len(_MANAGED_PERSONAS),
        "customers_created": customers_created,
        "payment_methods": payment_methods,
        "personas": [persona["name"] for persona in fixtures.ALL_PERSONAS],
        "bandit_priors_seeded": True,
        "bandit_prior_rows": priors["rows"],
        "causal_dag_nodes": dag_nodes,
    }


# ---------------------------------------------------------------------------
# Demo bandit priors
#
# A bandit with no history explores, which is correct and is the wrong thing to
# watch in a two-minute demo: the agent would pick an arm at random and the
# story "it learned that silent retries beat late-night nudges" would have
# nothing behind it. These priors are the *evidence a merchant would have
# accumulated over a few hundred cases*, seeded so the demo starts where a real
# deployment arrives after a month.
#
# **The bucket strings are computed, never written down.** Each entry names the
# persona and the scenario payload, and the bucket is derived by running the
# same `extract_context_vector` -> `make_context_bucket` the agent runs. Writing
# the strings as literals is how a seed silently stops matching the bucket the
# loop computes — the priors land in a context nothing ever looks up, every
# scenario cold-starts, and nothing about it looks broken.
#
# Counts are Beta(alpha, beta) with alpha = recoveries and beta = failures. The
# spreads are wide enough that the intended arm dominates a Thompson draw
# without being so lopsided that exploration stops entirely.
# ---------------------------------------------------------------------------

_DEMO_PRIORS: list[dict[str, Any]] = [
    {
        # S1 — Suresh. The salary-cycle save: wait for the money, then nudge.
        "persona": fixtures.PERSONA_SURESH,
        "payload": _payload_S1,
        "playbook": "subscription_failure",
        "amount_at_risk_cents": 299900,
        "arms": {
            "retry_at_inferred_date_plus_whatsapp_fallback": (18, 4),
            "retry_at_inferred_date": (14, 5),
            "whatsapp_payment_link_now": (10, 8),
            "immediate_retry": (6, 10),
            "human_handoff": (5, 7),
            "dunning_email_sequence": (4, 10),
            "mandate_reregistration": (3, 5),
            "pause_with_winback": (2, 6),
        },
    },
    {
        # S2 — Priya. 8% is the discount this cart size responds to; 12% recovers
        # barely more and costs margin, which is why it sits just below.
        "persona": fixtures.PERSONA_PRIYA,
        "payload": _payload_S2,
        "playbook": "checkout_abandonment",
        "amount_at_risk_cents": 124000,
        "arms": {
            "whatsapp_saved_cart_8pct": (16, 6),
            "whatsapp_saved_cart_12pct": (14, 8),
            "whatsapp_saved_cart_5pct": (10, 8),
            "whatsapp_saved_cart_no_discount": (5, 11),
            "suggest_alternate_method": (5, 7),
            "sms_saved_cart": (4, 9),
            "email_saved_cart": (3, 10),
            "no_op": (1, 12),
        },
    },
    {
        # S3 — Aditya. Late-night HDFC card failures recover on their own by
        # morning; saying nothing beats every message.
        "persona": fixtures.PERSONA_ADITYA,
        "payload": _payload_S3,
        "playbook": "failed_payment",
        "amount_at_risk_cents": 84000,
        "arms": {
            "silent_retry_next_morning": (18, 4),
            "retry_at_optimal_hour": (15, 5),
            "whatsapp_payment_link": (8, 10),
            "switch_method_upi": (6, 8),
            "sms_payment_link": (5, 10),
            "retry_now": (4, 14),
            "email_payment_link": (3, 10),
            "no_op": (1, 8),
        },
    },
    {
        # S4 — Meera. A chronic-late payer who always pays: the graduated ladder
        # pulls the payment forward without spending an eight-year relationship.
        "persona": fixtures.PERSONA_MEERA,
        "payload": _payload_S4,
        "playbook": "b2b_overdue",
        "amount_at_risk_cents": 14500000,
        "arms": {
            "graduated_b2b_sequence": (15, 5),
            "firm_reminder_whatsapp_plus_email": (12, 7),
            "partial_payment_offer": (11, 7),
            "firm_reminder_whatsapp": (10, 8),
            "polite_reminder_whatsapp": (8, 10),
            "escalate_to_human_ar": (8, 12),
            "accept_promise_to_pay": (6, 6),
            # Not in the Phase 6 spec's list, which seeds 8 of this playbook's 9
            # arms. One arm left at the flat prior is not a small omission: an
            # untried arm out-draws a well-evidenced one often enough that S4
            # would pick it on a noticeable fraction of demo runs, for no reason
            # a viewer could see. A middling prior keeps it a real option
            # without letting it win on noise alone.
            "payment_plan_offer": (9, 9),
            "polite_reminder_email": (5, 10),
        },
    },
    {
        # S5 — Vikram. Not in the Phase 6 spec's four, added because the
        # scenario is reply-driven: scenarios.md has the bandit open with a
        # WhatsApp payment link, and the churn handoff only happens if the case
        # is still in flight when his reply lands. A retry arm would charge the
        # card, close the case as recovered, and there would be nothing left for
        # "cancel kar do" to stop.
        "persona": fixtures.PERSONA_VIKRAM,
        "payload": _payload_S5,
        "playbook": "subscription_failure",
        "amount_at_risk_cents": 199900,
        "arms": {
            "whatsapp_payment_link_now": (17, 5),
            "mandate_reregistration": (12, 7),
            "retry_at_inferred_date_plus_whatsapp_fallback": (7, 9),
            "human_handoff": (6, 8),
            "retry_at_inferred_date": (5, 12),
            "immediate_retry": (3, 14),
            "dunning_email_sequence": (3, 10),
            "pause_with_winback": (2, 7),
        },
    },
    {
        # S6 — Sana. Same reasoning as S5: the opt-out is the whole scenario and
        # it needs an open case to arrive at. scenarios.md opens with a WhatsApp
        # payment link here too.
        "persona": fixtures.PERSONA_SANA,
        "payload": _payload_S6,
        "playbook": "failed_payment",
        "amount_at_risk_cents": 68000,
        "arms": {
            "whatsapp_payment_link": (16, 6),
            "sms_payment_link": (11, 8),
            "switch_method_upi": (9, 9),
            "retry_at_optimal_hour": (7, 10),
            "email_payment_link": (5, 11),
            "silent_retry_next_morning": (5, 12),
            "retry_now": (3, 13),
            "no_op": (1, 10),
        },
    },
]


#: The time-of-day bands `context.make_context_bucket` can produce.
_PERIODS = ("morning", "afternoon", "evening", "night")


def _prior_context_buckets(entry: dict[str, Any]) -> list[str]:
    """Every bucket this scenario could be looked up under.

    Usually one. The exception is an event whose payload carries no timestamp of
    its own — ``invoice.overdue`` has ``due_date`` and ``days_overdue`` but
    nothing saying when anything was *attempted*, because nothing was. At
    runtime the period then falls back to ``events.received_at``, which is
    whenever the scenario happened to be fired, so a single seeded period would
    match only if the demo ran in that four-hour window. Those entries are
    seeded across all four bands.

    Costs 24 extra rows and removes a class of "works in the morning, breaks in
    the afternoon" failure that is close to impossible to diagnose from the UI —
    the arm just looks wrong, with no indication the priors were never found.
    """
    bucket = _prior_context_bucket(entry)
    if ":unknown:" not in bucket:
        return [bucket]
    return [bucket] + [bucket.replace(":unknown:", f":{period}:") for period in _PERIODS]


def _prior_context_bucket(entry: dict[str, Any]) -> str:
    """The bucket the agent will compute for this scenario, computed the same way."""
    persona = entry["persona"]
    payload = entry["payload"]()

    metadata = dict(persona.get("metadata") or {})
    metadata["past_events_summary"] = persona.get("past_events_summary")
    customer = {
        "ltv_cents": persona.get("ltv_cents", 0),
        "tenure_days": persona.get("tenure_days", 0),
        "metadata": metadata,
    }
    case = {
        "metadata": payload,
        "amount_at_risk_cents": entry["amount_at_risk_cents"],
    }
    return make_context_bucket(extract_context_vector(case, customer, {"payload": payload}))


async def seed_bandit_priors(supabase_client: Any, merchant_id: str) -> dict[str, Any]:
    """Give the demo scenarios the history a month of real traffic would have.

    Idempotent: ``write_posterior`` looks the row up on the table's UNIQUE tuple
    and updates in place, so reloading fixtures resets the priors to these
    values rather than stacking on top of whatever the demo has since learned.
    That reset is the point — a demo run should start from the same place twice.
    """
    buckets: dict[str, str] = {}
    rows = 0

    for entry in _DEMO_PRIORS:
        playbook = str(entry["playbook"])
        entry_buckets = _prior_context_buckets(entry)
        buckets[f"{playbook}:{entry['persona']['external_id']}"] = ",".join(entry_buckets)

        for bucket in entry_buckets:
            for arm_name, (alpha, beta) in entry["arms"].items():
                write_posterior(
                    supabase_client,
                    merchant_id,
                    playbook,
                    arm_name,
                    bucket,
                    alpha=float(alpha),
                    beta=float(beta),
                    # Every prior observation was a pull. Without this the arms
                    # would read as untried in the UI while carrying a confident
                    # posterior, which is the one combination that is never true.
                    n_pulls=int(alpha) + int(beta) - 2,
                )
                rows += 1

    log.info("simulator.bandit_priors_seeded", merchant_id=merchant_id, rows=rows, **buckets)
    return {"rows": rows, "buckets": buckets}


def _fixture_customer_ids(supabase_client: Any, merchant_id: str) -> list[str]:
    """Ids of this merchant's simulator-created customers."""
    result = (
        supabase_client.table("customers")
        .select("id")
        .eq("merchant_id", merchant_id)
        .eq("metadata->>is_simulator_fixture", "true")
        .execute()
    )
    return [str(row["id"]) for row in (result.data or [])]


def reset_fixtures_for_merchant(
    supabase_client: Any, merchant_id: str, trace_id: str
) -> dict[str, Any]:
    """Delete every simulator-created row for this merchant.

    Order matters, and not only for foreign keys. ``events`` has no cascade from
    ``recovery_cases`` — the FK points the other way — so events are deleted
    explicitly. Everything hanging off a case (decisions, attempts, replies,
    audit rows) goes when the case does.

    The final audit row is written *after* the deletes, so the trail records that
    a reset happened even though everything it referred to is gone.
    """
    customer_ids = _fixture_customer_ids(supabase_client, merchant_id)

    deleted: dict[str, int] = {
        "customer_replies": 0,
        "execution_attempts": 0,
        "agent_decisions": 0,
        "audit_events": 0,
        "recovery_cases": 0,
        "events": 0,
        "payment_methods": 0,
        "customers": 0,
    }

    if customer_ids:
        cases = (
            supabase_client.table("recovery_cases")
            .select("id")
            .eq("merchant_id", merchant_id)
            .in_("customer_id", customer_ids)
            .execute()
        )
        case_ids = [str(row["id"]) for row in (cases.data or [])]

        if case_ids:
            # Explicit rather than relying on cascade: the counts are what the
            # UI reports back, and a cascade deletes silently.
            for table in (
                "customer_replies",
                "execution_attempts",
                "agent_decisions",
                "audit_events",
            ):
                result = (
                    supabase_client.table(table)
                    .delete()
                    .eq("merchant_id", merchant_id)
                    .in_("case_id", case_ids)
                    .execute()
                )
                deleted[table] = len(result.data or [])

            result = (
                supabase_client.table("recovery_cases")
                .delete()
                .eq("merchant_id", merchant_id)
                .in_("id", case_ids)
                .execute()
            )
            deleted["recovery_cases"] = len(result.data or [])

        result = (
            supabase_client.table("events")
            .delete()
            .eq("merchant_id", merchant_id)
            .in_("customer_id", customer_ids)
            .execute()
        )
        deleted["events"] = len(result.data or [])

        result = (
            supabase_client.table("payment_methods")
            .delete()
            .in_("customer_id", customer_ids)
            .execute()
        )
        deleted["payment_methods"] = len(result.data or [])

        result = (
            supabase_client.table("customers")
            .delete()
            .eq("merchant_id", merchant_id)
            .in_("id", customer_ids)
            .execute()
        )
        deleted["customers"] = len(result.data or [])

    # Simulator audit rows that were never attached to a case — fixture loads,
    # the B3 burst — are keyed by event name rather than by case.
    result = (
        supabase_client.table("audit_events")
        .delete()
        .eq("merchant_id", merchant_id)
        .is_("case_id", "null")
        .in_("event", ["fixtures_loaded", "scenario_fired", "fixtures_reset"])
        .execute()
    )
    deleted["audit_events"] += len(result.data or [])

    supabase_client.table("audit_events").insert(
        {
            "case_id": None,
            "merchant_id": merchant_id,
            "actor": "system",
            "event": "fixtures_reset",
            "details": deleted,
            "trace_id": trace_id,
        }
    ).execute()

    log.info("simulator.fixtures_reset", merchant_id=merchant_id, **deleted)
    return deleted


def get_fixture_status(supabase_client: Any, merchant_id: str) -> dict[str, Any]:
    """Report what the simulator currently has loaded for this merchant."""
    customers = (
        supabase_client.table("customers")
        .select("id, name, external_id")
        .eq("merchant_id", merchant_id)
        .eq("metadata->>is_simulator_fixture", "true")
        .execute()
    )
    customer_rows = customers.data or []
    customer_ids = [str(row["id"]) for row in customer_rows]

    payment_method_count = 0
    event_count = 0
    case_count = 0
    if customer_ids:
        methods = (
            supabase_client.table("payment_methods")
            .select("id")
            .in_("customer_id", customer_ids)
            .execute()
        )
        payment_method_count = len(methods.data or [])

        events = (
            supabase_client.table("events")
            .select("id")
            .eq("merchant_id", merchant_id)
            .in_("customer_id", customer_ids)
            .execute()
        )
        event_count = len(events.data or [])

        cases = (
            supabase_client.table("recovery_cases")
            .select("id")
            .eq("merchant_id", merchant_id)
            .in_("customer_id", customer_ids)
            .execute()
        )
        case_count = len(cases.data or [])

    present = {str(row["external_id"]) for row in customer_rows}
    # "Loaded" means the six scripted personas are all present. The B3 cohort is
    # loaded alongside them but is not what the scenarios depend on.
    expected = {persona["external_id"] for persona in fixtures.ALL_PERSONAS}

    return {
        "loaded": expected.issubset(present),
        "counts": {
            "customers": len(customer_rows),
            "payment_methods": payment_method_count,
            "events": event_count,
            "cases": case_count,
        },
        "personas": [
            str(row["name"]) for row in customer_rows if str(row["external_id"]) in expected
        ],
    }
