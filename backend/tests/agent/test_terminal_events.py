"""Settlements closing the cases they settled.

This is the half of the loop that was missing before Phase 13: the agent could
mint a real payment link and never learn whether it was paid, so the arm it chose
was never credited. What matters here is the matching — the wrong case closing is
worse than no case closing — and the guards against a duplicate webhook posting a
second reward for one outcome.
"""

from typing import Any

import pytest

from app.agent.core import handle_terminal_event
from app.agent.steps.detect import detect_playbook, is_terminal_event
from tests.simulator.conftest import MERCHANT_ID, OTHER_MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase

CASE_ID = "aaaaaaaa-1111-2222-3333-444444444444"
CUSTOMER_ID = "bbbbbbbb-1111-2222-3333-444444444444"


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    fake.seed_merchant(OTHER_MERCHANT_ID)
    return fake


def seed_case(
    db: FakeSupabase,
    *,
    case_id: str = CASE_ID,
    merchant_id: str = MERCHANT_ID,
    status: str = "in_flight",
    amount: int = 299900,
    metadata: dict[str, Any] | None = None,
    customer_id: str | None = None,
    opened_at: str = "2026-01-01T00:00:00+00:00",
) -> dict[str, Any]:
    row = {
        "id": case_id,
        "merchant_id": merchant_id,
        "customer_id": customer_id,
        "playbook": "subscription_failure",
        "status": status,
        "amount_at_risk_cents": amount,
        "amount_recovered_cents": 0,
        "metadata": metadata or {},
        "opened_at": opened_at,
        "current_step": "listen",
    }
    db.rows("recovery_cases").append(row)
    return row


def event(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"id": "evt-1", "event_type": event_type, "payload": payload}


# ─────────────────────────────────────────────────────────────────────
# Routing
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "event_type", ["payment.captured", "subscription.charged", "payment_link.paid"]
)
def test_settlements_are_terminal_not_playbooks(event_type: str) -> None:
    """Routing one to a playbook would open a fresh recovery case against a
    customer who has just paid."""
    assert is_terminal_event(event_type) is True
    assert detect_playbook(event_type) is None


def test_failures_are_not_terminal() -> None:
    assert is_terminal_event("payment.failed") is False
    assert detect_playbook("payment.failed") == "failed_payment"


# ─────────────────────────────────────────────────────────────────────
# Matching
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_matched_by_notes_case_id(db: FakeSupabase) -> None:
    """The exact route: the agent stamps case_id on every link it mints."""
    seed_case(db)
    await handle_terminal_event(
        event("payment.captured", {"notes": {"case_id": CASE_ID}, "amount": 299900}),
        MERCHANT_ID,
        db,
        "trace",
    )

    case = db.find_one("recovery_cases", CASE_ID)
    assert case is not None
    assert case["status"] == "recovered"
    assert case["amount_recovered_cents"] == 299900
    assert case["closed_at"] is not None


@pytest.mark.asyncio
async def test_matched_by_subscription_id(db: FakeSupabase) -> None:
    seed_case(db, metadata={"subscription_id": "sub_REAL123"})
    await handle_terminal_event(
        event("subscription.charged", {"subscription_id": "sub_REAL123"}),
        MERCHANT_ID,
        db,
        "trace",
    )

    case = db.find_one("recovery_cases", CASE_ID)
    assert case is not None and case["status"] == "recovered"
    # No amount on the payload, so it falls back to the amount at risk.
    assert case["amount_recovered_cents"] == 299900


@pytest.mark.asyncio
async def test_matched_by_customer_takes_the_oldest_active_case(db: FakeSupabase) -> None:
    """A customer with two open cases and one payment is genuinely ambiguous."""
    db.rows("customers").append(
        {"id": CUSTOMER_ID, "merchant_id": MERCHANT_ID, "external_id": "cust_suresh"}
    )
    seed_case(db, case_id=CASE_ID, customer_id=CUSTOMER_ID, opened_at="2026-01-01T00:00:00+00:00")
    newer = "cccccccc-1111-2222-3333-444444444444"
    seed_case(db, case_id=newer, customer_id=CUSTOMER_ID, opened_at="2026-02-01T00:00:00+00:00")

    await handle_terminal_event(
        event("payment.captured", {"customer_id": "cust_suresh"}), MERCHANT_ID, db, "trace"
    )

    assert db.find_one("recovery_cases", CASE_ID)["status"] == "recovered"  # type: ignore[index]
    assert db.find_one("recovery_cases", newer)["status"] == "in_flight"  # type: ignore[index]


@pytest.mark.asyncio
async def test_unmatched_settlement_is_a_no_op(db: FakeSupabase) -> None:
    """Ordinary business also produces captured payments; most are not recoveries."""
    seed_case(db)
    await handle_terminal_event(
        event("payment.captured", {"notes": {"case_id": "no-such-case"}}),
        MERCHANT_ID,
        db,
        "trace",
    )

    assert db.find_one("recovery_cases", CASE_ID)["status"] == "in_flight"  # type: ignore[index]


# ─────────────────────────────────────────────────────────────────────
# Guards
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["recovered", "stopped", "failed", "holdout"])
@pytest.mark.asyncio
async def test_only_active_cases_are_closed(db: FakeSupabase, status: str) -> None:
    """A duplicate webhook must not post a second reward for one outcome, and a
    stopped case must not be reopened over a customer's opt-out."""
    seed_case(db, status=status, amount=299900)
    await handle_terminal_event(
        event("payment.captured", {"notes": {"case_id": CASE_ID}, "amount": 299900}),
        MERCHANT_ID,
        db,
        "trace",
    )

    case = db.find_one("recovery_cases", CASE_ID)
    assert case is not None
    assert case["status"] == status
    assert case["amount_recovered_cents"] == 0


@pytest.mark.asyncio
async def test_another_merchants_case_is_never_touched(db: FakeSupabase) -> None:
    """Every lookup is merchant-scoped. A settlement must not reach another account."""
    seed_case(db, merchant_id=OTHER_MERCHANT_ID)
    await handle_terminal_event(
        event("payment.captured", {"notes": {"case_id": CASE_ID}}), MERCHANT_ID, db, "trace"
    )

    assert db.find_one("recovery_cases", CASE_ID)["status"] == "in_flight"  # type: ignore[index]


@pytest.mark.asyncio
async def test_partial_payment_records_what_arrived(db: FakeSupabase) -> None:
    seed_case(db, amount=299900)
    await handle_terminal_event(
        event("payment.captured", {"notes": {"case_id": CASE_ID}, "amount": 100000}),
        MERCHANT_ID,
        db,
        "trace",
    )

    assert db.find_one("recovery_cases", CASE_ID)["amount_recovered_cents"] == 100000  # type: ignore[index]


@pytest.mark.asyncio
async def test_audit_row_records_how_the_case_was_matched(db: FakeSupabase) -> None:
    """The customer route is a guess, so it has to be visible rather than silent."""
    seed_case(db, metadata={"subscription_id": "sub_REAL123"})
    await handle_terminal_event(
        event("subscription.charged", {"subscription_id": "sub_REAL123"}),
        MERCHANT_ID,
        db,
        "trace",
    )

    audit_rows = db.rows("audit_events")
    terminal = [r for r in audit_rows if "terminal_event" in str(r.get("event"))]
    assert len(terminal) == 1
    assert terminal[0]["details"]["matched_by"] == "subscription_id"


@pytest.mark.asyncio
async def test_a_dead_database_does_not_raise(db: FakeSupabase, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """It runs off a webhook, and Razorpay retries anything that is not a 2xx."""

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("connection reset")

    monkeypatch.setattr(db, "table", boom)
    await handle_terminal_event(
        event("payment.captured", {"notes": {"case_id": CASE_ID}}), MERCHANT_ID, db, "trace"
    )
