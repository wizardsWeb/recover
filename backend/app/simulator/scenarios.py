"""The nine scripted demo scenarios.

Firing a scenario walks the same path a real webhook will in Phase 3:

1. ensure the persona customer exists,
2. build the event payload,
3. write it to ``events``,
4. open a ``recovery_cases`` row in its initial state,
5. record the firing in ``audit_events``.

Two things the agent does *not* get in Phase 2: a diagnosis and a decision.
Cases open at ``current_step='detect'`` with ``diagnosis=None`` and stay there —
Phase 4 picks them up. That is deliberate: an open case with no diagnosis is a
truthful representation of a system that has detected a leak and not yet
reasoned about it, and it means the simulator can be trusted end-to-end before
any agent code exists.

Scenarios are **not** idempotent. Each firing is a new event and a new case,
because that is what a second real failure would be. Only the customer row is
reused.
"""

from datetime import date
from collections.abc import Callable
from typing import Any

from app.logging import get_logger
from app.simulator import fixtures
from app.simulator.event_generator import (
    build_checkout_abandoned_event,
    build_invoice_overdue_event,
    build_payment_failed_event,
    build_subscription_charged_failed_event,
    get_or_create_customer,
)

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Shared writes
# ---------------------------------------------------------------------------


def _insert_event(
    supabase_client: Any,
    merchant_id: str,
    customer_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Write one row to ``events``.

    ``received_at`` is left to the column default — the payload's own timestamp
    is the *scripted* time the failure happened, which is not the same thing as
    when Recover learned about it, and the event log tails on the latter.
    """
    result = (
        supabase_client.table("events")
        .insert(
            {
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "event_type": event_type,
                "payload": payload,
            }
        )
        .execute()
    )
    return dict(result.data[0])


def _open_case(
    supabase_client: Any,
    merchant_id: str,
    customer_id: str,
    playbook: str,
    amount_at_risk_cents: int,
    trigger_event_id: str,
) -> dict[str, Any]:
    """Open a recovery case in its pre-diagnosis state."""
    result = (
        supabase_client.table("recovery_cases")
        .insert(
            {
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "playbook": playbook,
                "status": "open",
                "amount_at_risk_cents": amount_at_risk_cents,
                "current_step": "detect",
                "diagnosis": None,
                "trigger_event_id": trigger_event_id,
            }
        )
        .execute()
    )
    return dict(result.data[0])


def _audit(
    supabase_client: Any,
    merchant_id: str,
    case_id: str | None,
    trace_id: str,
    scenario_code: str,
    notes: str,
    **details: Any,
) -> None:
    """Record that a scenario was fired.

    Actor is ``system``: a simulator firing is not the agent acting and not a
    human acting, and conflating it with either would poison the audit trail the
    ROI and compliance views are built on.
    """
    supabase_client.table("audit_events").insert(
        {
            "case_id": case_id,
            "merchant_id": merchant_id,
            "actor": "system",
            "event": "scenario_fired",
            "details": {"scenario_code": scenario_code, "notes": notes, **details},
            "trace_id": trace_id,
        }
    ).execute()


def _fire(
    supabase_client: Any,
    merchant_id: str,
    trace_id: str,
    *,
    code: str,
    persona: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
    playbook: str,
    amount_at_risk_cents: int,
    notes: str,
) -> dict[str, Any]:
    """Run the five common steps and return the standard response body."""
    customer = get_or_create_customer(supabase_client, merchant_id, persona)
    event = _insert_event(
        supabase_client, merchant_id, customer["id"], event_type, payload
    )
    case = _open_case(
        supabase_client,
        merchant_id,
        customer["id"],
        playbook,
        amount_at_risk_cents,
        event["id"],
    )
    _audit(
        supabase_client,
        merchant_id,
        case["id"],
        trace_id,
        code,
        notes,
        event_id=event["id"],
        customer_external_id=persona["external_id"],
        playbook=playbook,
        amount_at_risk_cents=amount_at_risk_cents,
    )

    log.info(
        "simulator.scenario_fired",
        scenario_code=code,
        merchant_id=merchant_id,
        case_id=case["id"],
        event_id=event["id"],
    )
    return {
        "case_id": case["id"],
        "event_id": event["id"],
        "scenario_code": code,
        "message": f"Fired {code} — case opened for {persona['name']}.",
    }


# ---------------------------------------------------------------------------
# S1 — Suresh Iyer
# ---------------------------------------------------------------------------


def fire_scenario_S1(supabase_client: Any, merchant_id: str, trace_id: str) -> dict[str, Any]:
    """S1 Suresh — subscription mandate failure. See scenarios.md §S1.

    Fourth consecutive failure on the 1st, each previously recovered by hand a
    few days later. The pattern is the signal: his salary lands after the
    charge date, not that his instrument is broken.
    """
    payload = build_subscription_charged_failed_event(
        customer_external_id="cust_suresh_iyer",
        subscription_id="sub_zenith_aarav_jee",
        amount_cents=299900,
        failure_reason="insufficient_funds",
        method="upi",
        mandate_id="mand_icici_suresh_upi",
        bank="ICICI",
        merchant_ref=fixtures.MERCHANT_ZENITH,
        failure_code="BAD_REQUEST_ERROR",
        attempted_at="2026-09-01T10:32:14+05:30",
    )
    return _fire(
        supabase_client,
        merchant_id,
        trace_id,
        code="S1",
        persona=fixtures.PERSONA_SURESH,
        event_type="subscription.charged.failed",
        payload=payload,
        playbook="subscription_failure",
        amount_at_risk_cents=299900,
        notes="Fourth 1st-of-month mandate failure; salary-cycle mismatch expected.",
    )


# ---------------------------------------------------------------------------
# S2 — Priya Menon
# ---------------------------------------------------------------------------


def fire_scenario_S2(supabase_client: Any, merchant_id: str, trace_id: str) -> dict[str, Any]:
    """S2 Priya — cart abandoned at method selection. See scenarios.md §S2."""
    payload = build_checkout_abandoned_event(
        customer_external_id="cust_priya_menon",
        cart_value_cents=124000,
        items=[
            {"sku": "vc_serum_30ml", "name": "Vitamin C serum", "price": 64000, "qty": 1},
            {
                "sku": "hydra_moisturizer_50g",
                "name": "Hydra moisturizer",
                "price": 42000,
                "qty": 1,
            },
            {"sku": "spf50_sunscreen_60ml", "name": "SPF 50 sunscreen", "price": 28000, "qty": 1},
        ],
        dropoff_stage="method_selection",
        session_duration_seconds=252,
        merchant_ref=fixtures.MERCHANT_KAJAL,
        cart_id="cart_20260903_priya",
        abandoned_at="2026-09-03T20:14:33+05:30",
    )
    return _fire(
        supabase_client,
        merchant_id,
        trace_id,
        code="S2",
        persona=fixtures.PERSONA_PRIYA,
        event_type="checkout.abandoned",
        payload=payload,
        playbook="checkout_abandonment",
        amount_at_risk_cents=124000,
        notes="Returning customer, 4m12s session, dropped at method selection.",
    )


# ---------------------------------------------------------------------------
# S3 — Aditya Rao
# ---------------------------------------------------------------------------


def fire_scenario_S3(supabase_client: Any, merchant_id: str, trace_id: str) -> dict[str, Any]:
    """S3 Aditya — card auth failure at 11:34pm Saturday. See scenarios.md §S3.

    The timestamp is the scenario. HDFC credit cards degrade every weekend
    night; the right move is to say nothing and retry Monday morning.
    """
    payload = build_payment_failed_event(
        customer_external_id="cust_aditya_rao",
        amount_cents=84000,
        method="card",
        failure_code="AUTHENTICATION_FAILED",
        failure_reason="issuer_otp_timeout",
        extra={"card": {"issuer": "HDFC", "type": "credit", "network": "visa", "bin": "455673"}},
        merchant_ref=fixtures.MERCHANT_KAJAL,
        order_id="order_20260906_aditya",
        attempted_at="2026-09-06T23:34:12+05:30",
    )
    return _fire(
        supabase_client,
        merchant_id,
        trace_id,
        code="S3",
        persona=fixtures.PERSONA_ADITYA,
        event_type="payment.failed",
        payload=payload,
        playbook="failed_payment",
        amount_at_risk_cents=84000,
        notes="Saturday 23:34 issuer OTP timeout; normal weekend-night degradation.",
    )


# ---------------------------------------------------------------------------
# S4 — Meera Patil
# ---------------------------------------------------------------------------


def fire_scenario_S4(supabase_client: Any, merchant_id: str, trace_id: str) -> dict[str, Any]:
    """S4 Meera — invoice 12 days overdue. See scenarios.md §S4.

    A chronic-late payer who has never missed one in eight years. The value on
    offer is days pulled forward, not a recovery that would otherwise be lost.
    """
    payload = build_invoice_overdue_event(
        customer_external_id="cust_meera_rasoi_chain",
        invoice_id="INV-2026-08847",
        amount_cents=14500000,
        due_date=date(2026, 8, 20),
        days_overdue=12,
        invoice_description="60 crates cooking oil (Fortune sunflower)",
        merchant_ref=fixtures.MERCHANT_SHARMA,
    )
    return _fire(
        supabase_client,
        merchant_id,
        trace_id,
        code="S4",
        persona=fixtures.PERSONA_MEERA,
        event_type="invoice.overdue",
        payload=payload,
        playbook="b2b_overdue",
        amount_at_risk_cents=14500000,
        notes="12 days overdue; chronic-late payer, 47 prior invoices, all paid.",
    )


# ---------------------------------------------------------------------------
# S5 — Vikram Sethi
# ---------------------------------------------------------------------------


def fire_scenario_S5(supabase_client: Any, merchant_id: str, trace_id: str) -> dict[str, Any]:
    """S5 Vikram — mandate revoked, first failure in 18 months. See §S5.

    Fire this, then inject "bhaisaab beta ab coaching nahi le raha, cancel kar
    do please" from the reply injector to reach the handoff beat.
    """
    payload = build_subscription_charged_failed_event(
        customer_external_id="cust_vikram_sethi",
        subscription_id="sub_zenith_vikram_class9",
        amount_cents=199900,
        failure_reason="mandate_revoked",
        method="upi",
        mandate_id="mand_hdfc_vikram_upi",
        bank="HDFC",
        merchant_ref=fixtures.MERCHANT_ZENITH,
        attempted_at="2026-09-04T08:15:00+05:30",
    )
    return _fire(
        supabase_client,
        merchant_id,
        trace_id,
        code="S5",
        persona=fixtures.PERSONA_VIKRAM,
        event_type="subscription.charged.failed",
        payload=payload,
        playbook="subscription_failure",
        amount_at_risk_cents=199900,
        notes="High-LTV subscriber, first failure in 18 months, mandate revoked.",
    )


# ---------------------------------------------------------------------------
# S6 — Sana Khatri
# ---------------------------------------------------------------------------


def fire_scenario_S6(supabase_client: Any, merchant_id: str, trace_id: str) -> dict[str, Any]:
    """S6 Sana — UPI PSP timeout on a first order. See scenarios.md §S6.

    Fire this, then inject "STOP" to exercise the hard compliance path.
    """
    payload = build_payment_failed_event(
        customer_external_id="cust_sana_khatri",
        amount_cents=68000,
        method="upi",
        failure_code="PSP_TIMEOUT",
        bank="SBI",
        merchant_ref=fixtures.MERCHANT_KAJAL,
        order_id="order_20260905_sana",
        attempted_at="2026-09-05T14:22:00+05:30",
    )
    return _fire(
        supabase_client,
        merchant_id,
        trace_id,
        code="S6",
        persona=fixtures.PERSONA_SANA,
        event_type="payment.failed",
        payload=payload,
        playbook="failed_payment",
        amount_at_risk_cents=68000,
        notes="First-time customer, UPI PSP timeout; opts out on first contact.",
    )


# ---------------------------------------------------------------------------
# B3 — federated downtime burst
# ---------------------------------------------------------------------------


def fire_scenario_B3(supabase_client: Any, merchant_id: str, trace_id: str) -> dict[str, Any]:
    """B3 — inject SBI UPI failure events across 8 synthetic customers.

    One customer failing on SBI UPI is noise. Eight inside ninety seconds is a
    bank outage, and no single merchant can tell the two apart from their own
    data alone. This fires the burst; Phase 10's detector reads it.
    """
    case_ids: list[str] = []
    event_ids: list[str] = []

    for index, synthetic in enumerate(fixtures.B3_SYNTHETIC_CUSTOMERS):
        payload = build_payment_failed_event(
            customer_external_id=synthetic["external_id"],
            amount_cents=synthetic["amount_cents"],
            method="upi",
            failure_code="GATEWAY_ERROR",
            failure_reason="upi_psp_unavailable",
            bank="SBI",
            merchant_ref=fixtures.MERCHANT_KAJAL,
            order_id=f"order_20260910_b3_{index + 1:02d}",
            # Spread across the 90-second window the alert is computed over.
            attempted_at=f"2026-09-10T14:3{index // 6}:{(index * 11) % 60:02d}+05:30",
        )
        customer = get_or_create_customer(supabase_client, merchant_id, synthetic)
        event = _insert_event(
            supabase_client, merchant_id, customer["id"], "payment.failed", payload
        )
        case = _open_case(
            supabase_client,
            merchant_id,
            customer["id"],
            "failed_payment",
            synthetic["amount_cents"],
            event["id"],
        )
        case_ids.append(case["id"])
        event_ids.append(event["id"])

    _audit(
        supabase_client,
        merchant_id,
        None,
        trace_id,
        "B3",
        "SBI UPI degradation burst across 8 customers.",
        event_ids=event_ids,
        case_ids=case_ids,
        affected_bank="SBI",
        affected_method="upi",
    )

    log.info(
        "simulator.scenario_fired",
        scenario_code="B3",
        merchant_id=merchant_id,
        cases_created=len(case_ids),
    )
    return {
        "case_id": case_ids[0],
        "event_id": event_ids[0],
        "case_ids": case_ids,
        "event_ids": event_ids,
        "scenario_code": "B3",
        "message": f"Fired B3 — {len(event_ids)} SBI UPI failures across {len(case_ids)} cases.",
    }


# ---------------------------------------------------------------------------
# B1 / B2 — batch beats, not yet buildable
# ---------------------------------------------------------------------------

_BATCH_DEFERRED = (
    "Batch scenarios ship in Phase 11. They replay ~1,000 cases through a "
    "trained bandit and a fitted uplift model, neither of which exists yet — "
    "firing one now would draw a learning curve from nothing."
)


def fire_scenario_B1(supabase_client: Any, merchant_id: str, trace_id: str) -> dict[str, Any]:
    """B1 — batch bandit learning curve. Deferred to Phase 11.

    Writes nothing. A stub that quietly created rows would be worse than one
    that refuses, because the chart it fed would look real.
    """
    return {"case_id": None, "event_id": None, "scenario_code": "B1", "message": _BATCH_DEFERRED}


def fire_scenario_B2(supabase_client: Any, merchant_id: str, trace_id: str) -> dict[str, Any]:
    """B2 — uplift ROI panel. Deferred to Phase 11. Writes nothing."""
    return {"case_id": None, "event_id": None, "scenario_code": "B2", "message": _BATCH_DEFERRED}


#: Scenarios that are stubs — the API answers 202 for these instead of 200.
DEFERRED_SCENARIOS: frozenset[str] = frozenset({"B1", "B2"})

ScenarioFn = Callable[[Any, str, str], dict[str, Any]]

SCENARIO_REGISTRY: dict[str, ScenarioFn] = {
    "S1": fire_scenario_S1,
    "S2": fire_scenario_S2,
    "S3": fire_scenario_S3,
    "S4": fire_scenario_S4,
    "S5": fire_scenario_S5,
    "S6": fire_scenario_S6,
    "B1": fire_scenario_B1,
    "B2": fire_scenario_B2,
    "B3": fire_scenario_B3,
}


# ---------------------------------------------------------------------------
# Metadata — what the control panel renders before you fire anything
# ---------------------------------------------------------------------------

SCENARIO_METADATA: dict[str, dict[str, Any]] = {
    "S1": {
        "code": "S1",
        "persona_name": "Suresh Iyer",
        "persona_external_id": "cust_suresh_iyer",
        "merchant_context": "Zenith Learning",
        "playbook": "subscription_failure",
        "amount_at_risk_inr": 2999,
        "amount_at_risk_cents": 299900,
        "event_type": "subscription.charged.failed",
        "one_line_description": "Subscription mandate failure — salary-cycle mismatch save",
        "video_expected_path": "retry_at_inferred_date + WhatsApp fallback (Phase 6)",
        "deferred": False,
    },
    "S2": {
        "code": "S2",
        "persona_name": "Priya Menon",
        "persona_external_id": "cust_priya_menon",
        "merchant_context": "Kajal & Co.",
        "playbook": "checkout_abandonment",
        "amount_at_risk_inr": 1240,
        "amount_at_risk_cents": 124000,
        "event_type": "checkout.abandoned",
        "one_line_description": "Cart abandoned at checkout — bandit picks 8% discount",
        "video_expected_path": "whatsapp_saved_cart_8pct (Phase 6)",
        "deferred": False,
    },
    "S3": {
        "code": "S3",
        "persona_name": "Aditya Rao",
        "persona_external_id": "cust_aditya_rao",
        "merchant_context": "Kajal & Co.",
        "playbook": "failed_payment",
        "amount_at_risk_inr": 840,
        "amount_at_risk_cents": 84000,
        "event_type": "payment.failed",
        "one_line_description": "Late-night card failure — bandit stays silent until Monday",
        "video_expected_path": "silent_retry_next_morning (Phase 6)",
        "deferred": False,
    },
    "S4": {
        "code": "S4",
        "persona_name": "Meera Patil",
        "persona_external_id": "cust_meera_rasoi_chain",
        "merchant_context": "Sharma Distributors",
        "playbook": "b2b_overdue",
        "amount_at_risk_inr": 145000,
        "amount_at_risk_cents": 14500000,
        "event_type": "invoice.overdue",
        "one_line_description": "B2B invoice 12 days overdue — Hinglish promise-to-pay",
        "video_expected_path": "graduated_b2b_sequence (Phase 6)",
        "deferred": False,
    },
    "S5": {
        "code": "S5",
        "persona_name": "Vikram Sethi",
        "persona_external_id": "cust_vikram_sethi",
        "merchant_context": "Zenith Learning",
        "playbook": "subscription_failure",
        "amount_at_risk_inr": 1999,
        "amount_at_risk_cents": 199900,
        "event_type": "subscription.charged.failed",
        "one_line_description": "High-LTV churn signal — agent stops and hands off to a human",
        "video_expected_path": "whatsapp_payment_link_now, then human_handoff (Phase 6)",
        "deferred": False,
    },
    "S6": {
        "code": "S6",
        "persona_name": "Sana Khatri",
        "persona_external_id": "cust_sana_khatri",
        "merchant_context": "Kajal & Co.",
        "playbook": "failed_payment",
        "amount_at_risk_inr": 680,
        "amount_at_risk_cents": 68000,
        "event_type": "payment.failed",
        "one_line_description": "First-order UPI timeout — STOP reply triggers hard compliance halt",
        "video_expected_path": "whatsapp_payment_link, then consent revoked (Phase 6)",
        "deferred": False,
    },
    "B1": {
        "code": "B1",
        "persona_name": None,
        "persona_external_id": None,
        "merchant_context": "Cross-merchant",
        "playbook": None,
        "amount_at_risk_inr": None,
        "amount_at_risk_cents": None,
        "event_type": None,
        "one_line_description": "Bandit learning curve over 1,000 replayed cases",
        "video_expected_path": "Batch replay (Phase 11)",
        "deferred": True,
    },
    "B2": {
        "code": "B2",
        "persona_name": None,
        "persona_external_id": None,
        "merchant_context": "Cross-merchant",
        "playbook": None,
        "amount_at_risk_inr": None,
        "amount_at_risk_cents": None,
        "event_type": None,
        "one_line_description": "Uplift ROI — gross recovery versus incremental recovery",
        "video_expected_path": "Batch replay (Phase 11)",
        "deferred": True,
    },
    "B3": {
        "code": "B3",
        "persona_name": "8 synthetic customers",
        "persona_external_id": None,
        "merchant_context": "Cross-merchant (modelled within one merchant)",
        "playbook": "failed_payment",
        "amount_at_risk_inr": None,
        "amount_at_risk_cents": sum(c["amount_cents"] for c in fixtures.B3_SYNTHETIC_CUSTOMERS),
        "event_type": "payment.failed",
        "one_line_description": "SBI UPI outage — 8 failures in 90 seconds trip the network detector",
        "video_expected_path": "Platform-wide retry pause (Phase 10)",
        "deferred": False,
    },
}
