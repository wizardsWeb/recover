"""Tests for the guardrail engine.

These are the tests that matter most in Phase 4. Every other step is a stub that
will be replaced; this one is the deterministic veto that has to keep behaving
identically as the models land around it. Each test pins one rule, and the
assertions check the *reason* as well as the verdict — a check that blocks for
the wrong reason is a bug the verdict alone would hide.
"""

from datetime import UTC, timedelta
from typing import Any

import pytest

from app.agent import guardrail as guardrail_module
from app.agent.guardrail import run_guardrail
from tests.agent.conftest import (
    BUSINESS_HOURS_IST,
    QUIET_HOURS_IST,
    freeze_time,
    make_attempt,
    make_case,
    make_customer,
    make_event,
)
from tests.simulator.fake_supabase import FakeSupabase


def whatsapp_decision(**overrides: Any) -> dict[str, Any]:
    decision = {
        "action_type": "send_whatsapp",
        "action_params": {"channel": "whatsapp"},
    }
    decision.update(overrides)
    return decision


def retry_decision(**overrides: Any) -> dict[str, Any]:
    decision: dict[str, Any] = {"action_type": "retry_charge", "action_params": {}}
    decision.update(overrides)
    return decision


def checks_by_name(result: Any) -> dict[str, Any]:
    return {check.check_name: check for check in result.checks}


async def test_blocks_when_customer_has_opted_out(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An opt-out outranks every other consideration, including the hour."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(
        db,
        consent={
            "whatsapp": True,
            "sms": True,
            "email": True,
            "opted_out_at": "2026-09-14T12:00:00+00:00",
        },
    )
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])

    result = await run_guardrail(case, whatsapp_decision(), customer, db)

    assert result.verdict == "BLOCK"
    assert result.blocking_check == "explicit_opt_out"
    # Opt-out is check 1, so nothing after it should have run.
    assert [check.check_name for check in result.checks] == ["explicit_opt_out"]


async def test_blocks_messages_during_trai_quiet_hours(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """11:34pm IST is inside the 9pm–9am window, so no message may go out."""
    freeze_time(monkeypatch, guardrail_module, QUIET_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])

    result = await run_guardrail(case, whatsapp_decision(), customer, db)

    assert result.verdict == "BLOCK"
    assert result.blocking_check == "trai_quiet_hours"
    assert "quiet window" in (checks_by_name(result)["trai_quiet_hours"].reason or "")


async def test_silent_retry_is_allowed_during_quiet_hours(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Quiet hours govern *communications*. A silent retry wakes nobody.

    This is the case that makes the distinction earn its keep: blocking retries
    overnight would forfeit the single best recovery window a payments agent has.
    """
    freeze_time(monkeypatch, guardrail_module, QUIET_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])

    result = await run_guardrail(case, retry_decision(), customer, db)

    assert result.verdict == "PASS"
    assert checks_by_name(result)["trai_quiet_hours"].passed


async def test_passes_when_everything_is_in_order(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All nine checks run and are recorded on a clean pass."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])

    result = await run_guardrail(case, whatsapp_decision(), customer, db)

    assert result.verdict == "PASS"
    assert result.blocking_check is None
    assert len(result.checks) == 9
    assert all(check.passed for check in result.checks)


async def test_blocks_on_daily_message_limit(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """failed_payment allows two messages a day; the third is refused."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])
    sent_at = BUSINESS_HOURS_IST.astimezone(UTC) - timedelta(hours=1)
    make_attempt(db, case["id"], action_type="send_whatsapp", attempted_at=sent_at)
    make_attempt(db, case["id"], action_type="send_sms", attempted_at=sent_at)

    result = await run_guardrail(case, whatsapp_decision(), customer, db)

    assert result.verdict == "BLOCK"
    assert result.blocking_check == "trai_daily_message_limit"
    assert "2/2" in (checks_by_name(result)["trai_daily_message_limit"].reason or "")


async def test_failed_attempts_do_not_count_toward_the_daily_limit(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A message that never sent did not interrupt anyone, so it is not counted."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])
    sent_at = BUSINESS_HOURS_IST.astimezone(UTC) - timedelta(hours=1)
    make_attempt(
        db, case["id"], action_type="send_whatsapp", status="failure", attempted_at=sent_at
    )
    make_attempt(
        db, case["id"], action_type="send_sms", status="failure", attempted_at=sent_at
    )

    result = await run_guardrail(case, whatsapp_decision(), customer, db)

    assert result.verdict == "PASS"


async def test_blocks_retry_inside_the_rbi_spacing_window(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RBI requires 24 hours between mandate retries; two hours is not enough."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])
    make_attempt(
        db,
        case["id"],
        action_type="retry_charge",
        attempted_at=BUSINESS_HOURS_IST - timedelta(hours=2),
    )

    result = await run_guardrail(case, retry_decision(), customer, db)

    assert result.verdict == "BLOCK"
    assert result.blocking_check == "rbi_min_hours_between_retries"


async def test_blocks_on_the_rbi_per_cycle_retry_cap(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three retries in a billing cycle is the ceiling for a subscription mandate."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"], event_type="subscription.charged.failed")
    case = make_case(db, customer["id"], event["id"], playbook="subscription_failure")
    cycle_time = BUSINESS_HOURS_IST.astimezone(UTC) - timedelta(days=3)
    for _ in range(3):
        make_attempt(db, case["id"], action_type="retry_charge", attempted_at=cycle_time)

    result = await run_guardrail(case, retry_decision(), customer, db)

    assert result.verdict == "BLOCK"
    assert result.blocking_check == "rbi_mandate_retry_count"


async def test_blocks_once_the_attempt_budget_is_spent(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])
    old = BUSINESS_HOURS_IST.astimezone(UTC) - timedelta(days=2)
    for _ in range(3):
        make_attempt(db, case["id"], action_type="send_email", attempted_at=old)

    result = await run_guardrail(case, whatsapp_decision(), customer, db)

    assert result.verdict == "BLOCK"
    assert result.blocking_check == "max_total_attempts"


async def test_blocks_after_the_hard_stop_window(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """failed_payment gives up after seven days rather than nagging indefinitely."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(
        db,
        customer["id"],
        event["id"],
        opened_at=BUSINESS_HOURS_IST - timedelta(days=9),
    )

    result = await run_guardrail(case, whatsapp_decision(), customer, db)

    assert result.verdict == "BLOCK"
    assert result.blocking_check == "hard_stop_after_days"


async def test_downgrades_to_the_next_consented_channel(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No WhatsApp consent is a routing problem, not a reason to give up."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(
        db,
        consent={"whatsapp": False, "sms": True, "email": True, "opted_out_at": None},
    )
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])

    result = await run_guardrail(case, whatsapp_decision(), customer, db)

    assert result.verdict == "DOWNGRADE"
    assert result.blocking_check == "channel_consent"
    assert result.downgrade_to == "switch_to_sms"


async def test_blocks_when_no_channel_remains(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Email is last in the failed_payment chain, so its refusal has no fallback."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(
        db,
        consent={"whatsapp": True, "sms": True, "email": False, "opted_out_at": None},
    )
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])

    result = await run_guardrail(
        case, whatsapp_decision(action_params={"channel": "email"}), customer, db
    )

    assert result.verdict == "BLOCK"
    assert result.blocking_check == "channel_consent"


async def test_blocks_retries_into_a_bank_the_network_says_is_down(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An open network alert makes a retry a guaranteed waste of an RBI-limited attempt."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"], payload={"amount": 68000, "bank": "HDFC"})
    case = make_case(db, customer["id"], event["id"])
    case = {**case, "metadata": {"bank": "hdfc", "method": "CARD"}}
    db.insert_row(
        "network_alerts",
        {
            "alert_type": "downtime",
            "affected_bank": "HDFC",
            "affected_method": "card",
            "severity": "high",
            "resolved_at": None,
        },
    )

    result = await run_guardrail(case, retry_decision(), customer, db)

    assert result.verdict == "BLOCK"
    assert result.blocking_check == "network_bank_health"


async def test_resolved_network_alerts_do_not_block(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])
    case = {**case, "metadata": {"bank": "hdfc", "method": "card"}}
    db.insert_row(
        "network_alerts",
        {
            "alert_type": "downtime",
            "affected_bank": "HDFC",
            "affected_method": "card",
            "severity": "high",
            "resolved_at": "2026-09-14T08:00:00+00:00",
        },
    )

    result = await run_guardrail(case, retry_decision(), customer, db)

    assert result.verdict == "PASS"


async def test_naive_timestamps_do_not_crash_the_compliance_path(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timestamp with no offset is read as UTC rather than raising TypeError."""
    freeze_time(monkeypatch, guardrail_module, BUSINESS_HOURS_IST)
    customer = make_customer(db)
    event = make_event(db, customer["id"])
    case = make_case(db, customer["id"], event["id"])
    case = {**case, "opened_at": "2026-09-15T04:00:00"}

    result = await run_guardrail(case, whatsapp_decision(), customer, db)

    assert result.verdict == "PASS"
