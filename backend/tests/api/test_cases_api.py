"""Tests for the cases, audit and analytics routers.

These exercise the routers against the in-memory Supabase fake, which does not
enforce RLS — so what is asserted here is our own query logic: which merchant id
each route filters on, which orderings it applies, and what it returns when a
row is absent. Tenant isolation is a Postgres guarantee and is tested where it
lives, in ``supabase/tests/rls_isolation.sql``.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deps import get_current_user_id, get_user_supabase
from app.main import app
from tests.simulator.conftest import MERCHANT_ID, OTHER_MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    fake.seed_merchant(OTHER_MERCHANT_ID)
    return fake


@pytest.fixture
def client(db: FakeSupabase) -> Iterator[TestClient]:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def seed_case(
    db: FakeSupabase,
    *,
    merchant_id: str = MERCHANT_ID,
    status: str = "in_flight",
    playbook: str = "failed_payment",
    amount: int = 68000,
    recovered: int = 0,
) -> dict[str, Any]:
    customer = db.insert_row(
        "customers", {"merchant_id": merchant_id, "name": "Sana Khatri", "email": "s@x.com"}
    )
    return db.insert_row(
        "recovery_cases",
        {
            "merchant_id": merchant_id,
            "customer_id": customer["id"],
            "playbook": playbook,
            "status": status,
            "amount_at_risk_cents": amount,
            "amount_recovered_cents": recovered,
        },
    )


def test_list_cases_returns_only_this_merchants_cases(client: TestClient, db: FakeSupabase) -> None:
    mine = seed_case(db)
    seed_case(db, merchant_id=OTHER_MERCHANT_ID)

    body = client.get("/api/cases").json()

    assert [c["id"] for c in body["cases"]] == [mine["id"]]
    assert body["limit"] == 50 and body["offset"] == 0


def test_list_cases_filters_by_status_and_playbook(client: TestClient, db: FakeSupabase) -> None:
    seed_case(db, status="stopped")
    wanted = seed_case(db, status="in_flight", playbook="b2b_overdue")

    body = client.get("/api/cases?status=in_flight&playbook=b2b_overdue").json()

    assert [c["id"] for c in body["cases"]] == [wanted["id"]]


def test_list_cases_paginates(client: TestClient, db: FakeSupabase) -> None:
    for _ in range(5):
        seed_case(db)

    first = client.get("/api/cases?limit=2").json()["cases"]
    second = client.get("/api/cases?limit=2&offset=2").json()["cases"]

    assert len(first) == 2 and len(second) == 2
    assert {c["id"] for c in first}.isdisjoint({c["id"] for c in second})


def test_list_cases_rejects_an_oversized_limit(client: TestClient) -> None:
    assert client.get("/api/cases?limit=500").status_code == 422


def test_get_case_returns_the_full_trail(client: TestClient, db: FakeSupabase) -> None:
    case = seed_case(db)
    db.insert_row(
        "audit_events",
        {
            "case_id": case["id"],
            "merchant_id": MERCHANT_ID,
            "actor": "agent",
            "event": "detect:case_opened",
            "details": {},
        },
    )
    db.insert_row(
        "execution_attempts",
        {
            "case_id": case["id"],
            "merchant_id": MERCHANT_ID,
            "action_type": "retry_charge",
            "adapter": "razorpay_subscriptions_simulated",
            "status": "success",
        },
    )

    body = client.get(f"/api/cases/{case['id']}").json()

    assert body["id"] == case["id"]
    assert len(body["audit_events"]) == 1
    assert len(body["execution_attempts"]) == 1
    # Present and empty, not absent — the frontend maps over all four.
    assert body["agent_decisions"] == []
    assert body["customer_replies"] == []


def test_get_case_404s_for_another_merchants_case(client: TestClient, db: FakeSupabase) -> None:
    """Not-yours and not-real get the same answer, so the API leaks no existence."""
    theirs = seed_case(db, merchant_id=OTHER_MERCHANT_ID)

    assert client.get(f"/api/cases/{theirs['id']}").status_code == 404


def test_override_stops_a_case_and_audits_the_human(client: TestClient, db: FakeSupabase) -> None:
    case = seed_case(db)

    body = client.post(
        f"/api/cases/{case['id']}/override",
        json={"action": "stop", "reason": "Customer called in"},
    ).json()

    assert body["new_status"] == "stopped"
    updated = db.find_one("recovery_cases", case["id"])
    assert updated is not None
    assert updated["status"] == "stopped"
    assert updated["current_step"] == "human_stop"

    audit_row = db.rows("audit_events")[-1]
    assert audit_row["actor"] == "human"
    assert audit_row["event"] == "human_override:stop"
    assert audit_row["details"]["reason"] == "Customer called in"


def test_override_rejects_an_unknown_action(client: TestClient, db: FakeSupabase) -> None:
    case = seed_case(db)

    response = client.post(f"/api/cases/{case['id']}/override", json={"action": "delete"})

    assert response.status_code == 422


def test_audit_list_filters_by_case_and_event_prefix(client: TestClient, db: FakeSupabase) -> None:
    case = seed_case(db)
    for event in ("detect:case_opened", "guardrail:guardrail_block", "execute:attempted"):
        db.insert_row(
            "audit_events",
            {
                "case_id": case["id"],
                "merchant_id": MERCHANT_ID,
                "actor": "agent",
                "event": event,
                "details": {},
            },
        )

    body = client.get(f"/api/audit?case_id={case['id']}&event_prefix=guardrail").json()

    assert [e["event"] for e in body["audit_events"]] == ["guardrail:guardrail_block"]


def test_overview_summarises_todays_money(client: TestClient, db: FakeSupabase) -> None:
    seed_case(db, amount=68000, recovered=0, status="in_flight")
    seed_case(db, amount=32000, recovered=32000, status="recovered")

    body = client.get("/api/analytics/overview").json()

    assert body["cases_opened_today"] == 2
    assert body["cases_in_flight"] == 1
    assert body["amount_at_risk_today_cents"] == 100000
    assert body["amount_recovered_today_cents"] == 32000
    assert body["recovery_rate_today"] == 0.5
    assert body["compliance_violations_today"] == 0


def test_overview_survives_a_merchant_with_no_cases(client: TestClient) -> None:
    """Division by zero is the obvious way this endpoint breaks on day one."""
    body = client.get("/api/analytics/overview").json()

    assert body["recovery_rate_today"] == 0.0
    assert body["amount_at_risk_today_cents"] == 0
