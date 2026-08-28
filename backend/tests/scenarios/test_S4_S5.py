"""S4 Meera and S5 Vikram end to end — the two scenarios that do not end in money.

Phases 1-6 proved the agent can recover. These two prove it can stop, which is
the harder half and the one a recovery product gets wrong.

* **S4** — Meera answers a firm reminder with "50% abhi kar deti hoon, baaki 25
  tak". That is neither payment nor refusal, and the case must stay open with
  the terms recorded. An agent that closed it as recovered would book money that
  has not arrived; one that closed it as stopped would abandon a customer who
  just said she would pay.
* **S5** — Vikram says cancel. The agent stops immediately and leaves a briefing
  a retention team can act on. scenarios.md is explicit that the win here is ₹0
  recovered and a ₹36,000 customer kept.

Both run against the pattern-matching fallback, because ``GEMINI_API_KEY`` is
unset in CI. That is deliberate coverage rather than a limitation: it is the
path that runs during a Gemini outage, and it is the one where a misread
"cancel" would revoke consent instead of triggering a handoff.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent.core import process_event
from app.deps import get_current_user_id, get_user_supabase
from app.main import app
from tests.simulator.conftest import MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    return fake


@pytest.fixture
def client(db: FakeSupabase, monkeypatch: pytest.MonkeyPatch) -> Any:
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    monkeypatch.setattr("app.api.simulator.get_service_client", lambda: db)
    monkeypatch.setattr("app.api.events.get_service_client", lambda: db)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def rows_for(db: FakeSupabase, table: str, case_id: str) -> list[dict[str, Any]]:
    return [row for row in db.rows(table) if row.get("case_id") == case_id]


def audit_events(db: FakeSupabase, case_id: str) -> list[str]:
    return [row["event"] for row in rows_for(db, "audit_events", case_id)]


def fire(client: TestClient, code: str) -> dict[str, Any]:
    loaded = client.post("/api/simulator/fixtures/load")
    assert loaded.status_code == 200, loaded.text
    fired = client.post(f"/api/simulator/scenarios/{code}")
    assert fired.status_code == 200, fired.text
    return dict(fired.json())


def inject(client: TestClient, case_id: str, text: str) -> None:
    resp = client.post(
        "/api/simulator/replies",
        json={"caseId": case_id, "channel": "whatsapp", "rawText": text},
    )
    assert resp.status_code == 200, resp.text


# ── S4 — Meera: the graduated ladder and the promise ───────────────────


async def test_s4_fires_the_day_twelve_rung_as_two_separate_attempts(
    client: TestClient, db: FakeSupabase
) -> None:
    fired = fire(client, "S4")
    case_id = fired["caseId"]

    decision = rows_for(db, "agent_decisions", case_id)[0]
    assert decision["bandit_chosen_arm"] == "graduated_b2b_sequence"

    # Twelve days overdue lands on the firm rung: WhatsApp plus email.
    attempts = rows_for(db, "execution_attempts", case_id)
    assert [a["action_type"] for a in attempts] == ["send_whatsapp", "send_email"]

    # One row per send, not one row for the sequence. These rows are what the
    # TRAI frequency check counts; collapsing them would understate the cap.
    assert len({a["idempotency_key"] for a in attempts}) == 2

    case = db.find_one("recovery_cases", case_id)
    assert case is not None
    assert case["status"] == "in_flight"


async def test_s4_message_names_the_customer_and_the_invoice(
    client: TestClient, db: FakeSupabase
) -> None:
    """The body reaches the attempt row whether or not Gemini answered.

    Without an API key the copy is the neutral fallback template, so this asserts
    the plumbing — a body is present on every send — rather than the wording,
    which is the model's and is not reproducible in CI.
    """
    fired = fire(client, "S4")
    attempts = rows_for(db, "execution_attempts", fired["caseId"])

    for attempt in attempts:
        assert attempt["request_payload"]["body"]
        assert attempt["response_payload"]["message_generation"]["tone"]


async def test_s4_promise_to_pay_is_recorded_and_the_case_stays_open(
    client: TestClient, db: FakeSupabase
) -> None:
    fired = fire(client, "S4")
    case_id, event_id = fired["caseId"], fired["eventId"]

    inject(client, case_id, "boss, 50% abhi kar deti hoon, baaki 25 tak")
    result = await process_event(event_id, MERCHANT_ID, db)

    assert result is not None
    assert result.listen is not None
    assert result.listen.intent == "promise_to_pay"

    case = db.find_one("recovery_cases", case_id)
    assert case is not None
    promise = case["metadata"]["promise_to_pay"]
    assert promise["partial_pct"] == 50
    assert promise["date_hint"] == "25 tak"
    assert promise["raw_reply"] == "boss, 50% abhi kar deti hoon, baaki 25 tak"

    # The case is neither recovered nor stopped — it is waiting.
    assert case["status"] == "in_flight"
    assert case["current_step"] == "awaiting_promise"
    assert case["closed_at"] is None

    assert "listen:promise_tracked" in audit_events(db, case_id)

    # Nothing was rewarded: no money has arrived, so no arm has an outcome yet.
    assert [r for r in db.rows("bandit_rewards") if r["case_id"] == case_id] == []


# ── S5 — Vikram: stopping, and handing over well ───────────────────────


async def test_s5_churn_stops_the_case_and_leaves_a_briefing(
    client: TestClient, db: FakeSupabase
) -> None:
    fired = fire(client, "S5")
    case_id, event_id = fired["caseId"], fired["eventId"]

    inject(client, case_id, "bhaisaab beta ab coaching nahi le raha, cancel kar do please")
    result = await process_event(event_id, MERCHANT_ID, db)

    assert result is not None
    assert result.listen is not None
    # Churn, not an opt-out. Reading this as "stop messaging me" would revoke
    # consent on every channel for a customer who only wanted to end one service.
    assert result.listen.intent == "churn_confirmation"
    assert result.listen.churn_signal is True
    assert result.listen.opt_out_signal is False

    case = db.find_one("recovery_cases", case_id)
    assert case is not None
    assert case["status"] == "stopped"
    assert case["closed_at"] is not None

    handoffs = [
        a
        for a in rows_for(db, "execution_attempts", case_id)
        if a["action_type"] == "human_handoff"
    ]
    assert len(handoffs) == 1
    payload = handoffs[0]["request_payload"]

    assert payload["reason"] == "churn"
    assert payload["suggested_retention_actions"] == [
        "offer_3_month_pause",
        "downgrade_to_cheaper_tier",
        "schedule_retention_call",
    ]
    # The numbers that make a retention call worth making: 18 months, Rs 36,000.
    assert payload["customer"]["ltv_cents"] == 3600000
    assert payload["customer"]["tenure_days"] == 547
    assert payload["customer"]["name"] == "Vikram Sethi"
    # His own words, so the call can open from what he actually said.
    assert "coaching nahi le raha" in payload["customer_reply"]

    trail = audit_events(db, case_id)
    assert "listen:reply_classified" in trail
    assert trail[-1] == "audit:case_closed"


async def test_s5_consent_survives_a_churn_reply(client: TestClient, db: FakeSupabase) -> None:
    """Ending a subscription is not withdrawing permission to be contacted.

    Vikram may well buy again next year. Revoking his consent because he
    cancelled one service would make that impossible and would be a worse
    outcome than the churn itself.
    """
    fired = fire(client, "S5")
    inject(client, fired["caseId"], "bhaisaab beta ab coaching nahi le raha, cancel kar do please")
    await process_event(fired["eventId"], MERCHANT_ID, db)

    vikram = [c for c in db.rows("customers") if c["external_id"] == "cust_vikram_sethi"][0]
    assert vikram["consent"]["whatsapp"] is True
    assert vikram["consent"]["opted_out_at"] is None


async def test_s5_hardship_offers_different_retention_actions(
    client: TestClient, db: FakeSupabase
) -> None:
    """Someone struggling needs pressure removed, not a reason to stay."""
    fired = fire(client, "S5")
    inject(client, fired["caseId"], "papa ki tabiyat kharab hai, next month kar dunga")
    await process_event(fired["eventId"], MERCHANT_ID, db)

    handoff = [
        a
        for a in rows_for(db, "execution_attempts", fired["caseId"])
        if a["action_type"] == "human_handoff"
    ][0]

    assert handoff["request_payload"]["reason"] == "hardship"
    assert "offer_payment_plan" in handoff["request_payload"]["suggested_retention_actions"]
