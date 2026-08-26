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

from typing import Any

from app.logging import get_logger
from app.simulator import fixtures
from app.simulator.event_generator import get_or_create_customer

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


def load_fixtures_for_merchant(
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
    }


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
            str(row["name"])
            for row in customer_rows
            if str(row["external_id"]) in expected
        ],
    }
