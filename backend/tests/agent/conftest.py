"""Fixtures for the agent loop tests.

The agent is tested against the same in-memory Supabase stand-in the simulator
uses. That is a deliberate trade: it does not enforce RLS or the schema (see
``tests/simulator/fake_supabase``), but the logic under test here — which check
fires, in what order, and what gets written — is entirely our own, and running
it against a live project would buy fidelity we do not need at the cost of a
network round trip per assertion.

Time is the other thing that has to be controlled. Half the guardrail's checks
read the wall clock, and a test that passes at 10am and fails at 10pm is worse
than no test. ``freeze_time`` pins ``datetime.now`` inside one module.
"""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.simulator.fake_supabase import FakeSupabase

IST = ZoneInfo("Asia/Kolkata")

MERCHANT_ID = "11111111-1111-4111-8111-111111111111"

#: A weekday mid-morning in IST — outside TRAI quiet hours, so a test that is
#: not about quiet hours is never accidentally about quiet hours.
BUSINESS_HOURS_IST = datetime(2026, 9, 15, 10, 30, tzinfo=IST)

#: Late enough to be inside the 9pm–9am quiet window.
QUIET_HOURS_IST = datetime(2026, 9, 15, 23, 34, tzinfo=IST)


def freeze_time(monkeypatch: pytest.MonkeyPatch, module: Any, when: datetime) -> None:
    """Pin ``datetime.now`` inside ``module`` to ``when``.

    Patching the module's ``datetime`` name rather than the clock globally keeps
    the blast radius to the module under test — the fake database keeps its own
    monotonic timestamps, which is what makes ``order by ... desc`` deterministic.
    """

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            return when.astimezone(tz) if tz else when.replace(tzinfo=None)

    monkeypatch.setattr(module, "datetime", _Frozen)


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    return fake


def make_customer(
    db: FakeSupabase,
    *,
    consent: dict[str, Any] | None = None,
    name: str = "Sana Iqbal",
) -> dict[str, Any]:
    """Insert a customer, fully opted in unless told otherwise."""
    return db.insert_row(
        "customers",
        {
            "merchant_id": MERCHANT_ID,
            "external_id": "cust_test",
            "name": name,
            "phone": "+919812345678",
            "email": "sana@example.com",
            "consent": consent
            if consent is not None
            else {
                "whatsapp": True,
                "sms": True,
                "email": True,
                "marketing": False,
                "opted_out_at": None,
            },
        },
    )


def make_event(
    db: FakeSupabase,
    customer_id: str,
    *,
    event_type: str = "payment.failed",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return db.insert_row(
        "events",
        {
            "merchant_id": MERCHANT_ID,
            "customer_id": customer_id,
            "event_type": event_type,
            "payload": payload if payload is not None else {"amount": 68000, "method": "card"},
        },
    )


def make_case(
    db: FakeSupabase,
    customer_id: str,
    event_id: str,
    *,
    playbook: str = "failed_payment",
    opened_at: datetime | None = None,
    amount_at_risk_cents: int = 68000,
) -> dict[str, Any]:
    return db.insert_row(
        "recovery_cases",
        {
            "merchant_id": MERCHANT_ID,
            "customer_id": customer_id,
            "playbook": playbook,
            "status": "open",
            "amount_at_risk_cents": amount_at_risk_cents,
            "current_step": "detect",
            "trigger_event_id": event_id,
            # Defaults are anchored to the frozen clock, not the wall clock: a
            # case "opened an hour ago" in real time is three weeks old relative
            # to a pinned September date, which would trip the hard-stop check
            # in every test that is not about the hard stop.
            "opened_at": (opened_at or BUSINESS_HOURS_IST - timedelta(hours=1)).isoformat(),
        },
    )


def make_attempt(
    db: FakeSupabase,
    case_id: str,
    *,
    action_type: str,
    status: str = "success",
    attempted_at: datetime | None = None,
) -> dict[str, Any]:
    return db.insert_row(
        "execution_attempts",
        {
            "case_id": case_id,
            "merchant_id": MERCHANT_ID,
            "action_type": action_type,
            "adapter": "test",
            "status": status,
            "attempted_at": (attempted_at or BUSINESS_HOURS_IST).isoformat(),
        },
    )


def audit_events(db: FakeSupabase, case_id: str) -> list[str]:
    """The ``event`` strings written for a case, in insertion order."""
    return [row["event"] for row in db.rows("audit_events") if row["case_id"] == case_id]
