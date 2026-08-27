"""End-to-end tests for the nine-step loop.

Phase 4's claim is that the loop runs start to finish and leaves a complete
trail behind it. These tests check that claim the way an auditor would: not by
inspecting return values alone, but by reading back what landed in
``audit_events``, ``agent_decisions`` and ``execution_attempts``.
"""

from typing import Any

import pytest

from app.agent import guardrail as guardrail_module
from app.agent.core import process_event, run_agent_loop
from app.agent.models import CaseStatus, DecisionSource, StepName
from app.agent.playbooks import CHECKOUT_ABANDONMENT_CONFIG
from tests.agent.conftest import (
    BUSINESS_HOURS_IST,
    MERCHANT_ID,
    QUIET_HOURS_IST,
    audit_events,
    freeze_time,
    make_case,
    make_customer,
    make_event,
)
from tests.simulator.fake_supabase import FakeSupabase

TRACE_ID = "trace0000000000000000000000000001"


def rows_for(db: FakeSupabase, table: str, case_id: str) -> list[dict[str, Any]]:
    return [row for row in db.rows(table) if row.get("case_id") == case_id]


@pytest.fixture(autouse=True)
def _pin_bandit(deterministic_bandit: None) -> None:
    """Every test in this module asserts on loop structure, not on arm sampling."""


async def test_loop_runs_all_nine_steps_and_leaves_a_full_trail(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clean checkout-abandonment case walks the whole loop and lands in flight."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(
        db, customer["id"], event_type="checkout.abandoned", payload={"cart_value": 124000}
    )
    case = make_case(db, customer["id"], event["id"], playbook="checkout_abandonment")

    result = await run_agent_loop(case, event, MERCHANT_ID, db, TRACE_ID)

    assert result.steps_completed == [
        StepName.DETECT,
        StepName.DIAGNOSE,
        StepName.UPLIFT_CHECK,
        StepName.DECIDE,
        StepName.GUARDRAIL,
        StepName.EXECUTE,
        StepName.LISTEN,
        StepName.LEARN,
        StepName.AUDIT,
    ]
    assert result.final_status is CaseStatus.IN_FLIGHT
    assert result.guardrail is not None and result.guardrail.verdict == "PASS"

    # The bandit decided, and said so. With no posteriors seeded every arm is at
    # its flat prior, so this asserts the shape of a bandit decision rather than
    # a particular winner — which arm a tie resolves to is not a property worth
    # freezing.
    assert result.decision is not None
    assert result.decision.decision_source is DecisionSource.BANDIT
    assert result.decision.is_stub is False
    assert result.decision.chosen_arm in CHECKOUT_ABANDONMENT_CONFIG.arms
    assert result.decision.bandit_mode in ("exploit", "explore")
    # Every arm is ranked, not just the winner — the counterfactual is what
    # makes the decision explainable.
    assert len(result.decision.alternatives_considered) == len(CHECKOUT_ABANDONMENT_CONFIG.arms)
    assert sum(alt.chosen for alt in result.decision.alternatives_considered) == 1
    # The context the arm was drawn under is carried on the result, because the
    # reward has to be credited back to this exact bucket.
    assert result.decision.bandit_context_vector["ltv_bucket"] == "low"

    # Every step that produces a fact wrote one audit row.
    assert audit_events(db, case["id"]) == [
        "detect:case_opened",
        "diagnose:diagnosis_complete",
        "uplift_check:uplift_verdict",
        "decide:decision_made",
        "guardrail:guardrail_pass",
        "execute:execution_attempted",
        # Listen is audited even with no reply waiting, so the trail always shows
        # that the agent looked.
        "listen:reply_classified",
    ]

    attempts = rows_for(db, "execution_attempts", case["id"])
    assert len(attempts) == 1
    assert attempts[0]["action_type"] == "send_whatsapp"
    assert attempts[0]["adapter"] == "whatsapp_business_simulated"

    decisions = rows_for(db, "agent_decisions", case["id"])
    assert len(decisions) == 1
    # step_number is the decide step's position in the nine-step loop, not the
    # Nth decision on this case.
    assert decisions[0]["step_number"] == 4
    assert decisions[0]["decision_source"] == "bandit"
    # The counterfactual is recorded, not just the winner.
    assert len(decisions[0]["bandit_alternatives"]) == 8
    # And the context bucket the draw came from, so the reward posted when this
    # case closes lands on the same posterior.
    assert decisions[0]["bandit_context_vector"]["ltv_bucket"] == "low"

    stored_case = db.find_one("recovery_cases", case["id"])
    assert stored_case is not None
    assert stored_case["status"] == "in_flight"
    assert stored_case["diagnosis"]["root_cause"] == "price_sensitivity_at_checkout"
    assert stored_case["uplift_bucket"] == "persuadable"

    stored_event = db.find_one("events", event["id"])
    assert stored_event is not None and stored_event["processed_at"] is not None


async def test_stop_reply_revokes_consent_and_stops_the_case(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario S6: the customer replies STOP and the agent must never contact them again."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(
        db, customer["id"], event_type="checkout.abandoned", payload={"cart_value": 124000}
    )
    case = make_case(db, customer["id"], event["id"], playbook="checkout_abandonment")
    db.insert_row(
        "customer_replies",
        {
            "case_id": case["id"],
            "merchant_id": MERCHANT_ID,
            "customer_id": customer["id"],
            "channel": "whatsapp",
            "raw_text": "STOP",
        },
    )

    result = await run_agent_loop(case, event, MERCHANT_ID, db, TRACE_ID)

    assert result.listen is not None
    assert result.listen.opt_out_signal is True
    assert result.final_status is CaseStatus.STOPPED

    updated_customer = db.find_one("customers", customer["id"])
    assert updated_customer is not None
    consent = updated_customer["consent"]
    assert consent["opted_out_at"] is not None
    assert consent["whatsapp"] is False and consent["sms"] is False and consent["email"] is False

    trail = audit_events(db, case["id"])
    assert "listen:reply_classified" in trail
    assert "listen:consent_revoked" in trail
    assert trail[-1] == "audit:case_closed"

    # The reply is marked handled so a second pass cannot re-apply it.
    reply = rows_for(db, "customer_replies", case["id"])[0]
    assert reply["applied_state_update"] == "REVOKE_CONSENT_ALL_CHANNELS"


async def test_a_blocked_guardrail_stops_the_case_without_executing(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quiet hours end the pass at step 5 — nothing is sent and the trail says why."""
    freeze_time(monkeypatch, guardrail_module, QUIET_HOURS_IST)
    customer = make_customer(db)
    event = make_event(
        db, customer["id"], event_type="checkout.abandoned", payload={"cart_value": 124000}
    )
    case = make_case(db, customer["id"], event["id"], playbook="checkout_abandonment")

    result = await run_agent_loop(case, event, MERCHANT_ID, db, TRACE_ID)

    assert result.final_status is CaseStatus.STOPPED
    assert result.steps_completed[-1] is StepName.AUDIT
    assert StepName.EXECUTE not in result.steps_completed
    assert result.guardrail is not None
    assert result.guardrail.blocking_check == "trai_quiet_hours"

    assert rows_for(db, "execution_attempts", case["id"]) == []
    assert "guardrail:guardrail_block" in audit_events(db, case["id"])

    stored_case = db.find_one("recovery_cases", case["id"])
    assert stored_case is not None and stored_case["status"] == "stopped"


async def test_downgrade_reroutes_to_a_consented_channel(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No WhatsApp consent downgrades to email, and the re-check is what clears it."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(
        db, consent={"whatsapp": False, "sms": True, "email": True, "opted_out_at": None}
    )
    event = make_event(
        db, customer["id"], event_type="checkout.abandoned", payload={"cart_value": 124000}
    )
    case = make_case(db, customer["id"], event["id"], playbook="checkout_abandonment")

    result = await run_agent_loop(case, event, MERCHANT_ID, db, TRACE_ID)

    assert result.guardrail is not None and result.guardrail.verdict == "PASS"
    assert result.final_status is CaseStatus.IN_FLIGHT

    attempt = rows_for(db, "execution_attempts", case["id"])[0]
    assert attempt["request_payload"]["components"]["channel"] == "email"

    # Both guardrail passes are on the record: the downgrade and the re-check.
    trail = audit_events(db, case["id"])
    assert trail.count("guardrail:guardrail_downgrade") == 1
    assert trail.count("guardrail:guardrail_pass") == 1


async def test_execution_is_idempotent_within_a_trace(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-running the same pass must not send the message twice.

    This is the property that makes the loop safe to run from a background task
    a webhook may deliver more than once.
    """
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(
        db, customer["id"], event_type="checkout.abandoned", payload={"cart_value": 124000}
    )
    case = make_case(db, customer["id"], event["id"], playbook="checkout_abandonment")

    await run_agent_loop(case, event, MERCHANT_ID, db, TRACE_ID)
    second = await run_agent_loop(case, event, MERCHANT_ID, db, TRACE_ID)

    assert len(rows_for(db, "execution_attempts", case["id"])) == 1
    assert second.execution is not None
    assert second.execution.adapter == "idempotency_cache"


async def test_process_event_reuses_the_case_the_simulator_opened(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])

    result = await process_event(event["id"], MERCHANT_ID, db)

    assert result is not None
    assert result.case_id == case["id"]
    assert len(db.rows("recovery_cases")) == 1


async def test_process_event_opens_a_case_for_a_raw_webhook(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real Razorpay event arrives with no case attached; the agent opens one."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"], payload={"amount": 84000, "method": "upi"})

    result = await process_event(event["id"], MERCHANT_ID, db)

    assert result is not None
    cases = db.rows("recovery_cases")
    assert len(cases) == 1
    assert cases[0]["playbook"] == "failed_payment"
    assert cases[0]["amount_at_risk_cents"] == 84000


async def test_process_event_ignores_event_types_with_no_playbook(db: FakeSupabase) -> None:
    """``customer.replied`` has no playbook; dropping it must not raise."""
    customer = make_customer(db)
    event = make_event(db, customer["id"], event_type="customer.replied", payload={})

    assert await process_event(event["id"], MERCHANT_ID, db) is None
    assert db.rows("recovery_cases") == []


async def test_process_event_ignores_a_missing_event(db: FakeSupabase) -> None:
    assert await process_event("00000000-0000-4000-8000-000000000000", MERCHANT_ID, db) is None


async def test_a_step_failure_is_recorded_rather_than_lost(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The loop runs detached, so an exception has to end up in the trail.

    Without the catch, a failure inside a BackgroundTask disappears into the
    task runner and the case sits at ``open`` with no explanation.
    """
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("gemini exploded")

    monkeypatch.setattr("app.agent.core.run_diagnose", boom)

    result = await run_agent_loop(case, event, MERCHANT_ID, db, TRACE_ID)

    assert result.final_status is CaseStatus.FAILED
    assert result.error == "gemini exploded"
    assert "audit:loop_failed" in audit_events(db, case["id"])
