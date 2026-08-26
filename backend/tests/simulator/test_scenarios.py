"""Firing scenarios: what lands in the database, and what refuses to."""

import pytest
from fastapi.testclient import TestClient

from app.simulator.scenarios import SCENARIO_METADATA
from tests.simulator.conftest import MERCHANT_ID, rows
from tests.simulator.fake_supabase import FakeSupabase

#: The six scripted scenarios — the ones that write an event and open a case.
SCRIPTED = ["S1", "S2", "S3", "S4", "S5", "S6"]


def test_fire_S1_creates_case_and_event(loaded_client: TestClient, db: FakeSupabase) -> None:
    response = loaded_client.post("/api/simulator/scenarios/S1")

    assert response.status_code == 200, response.text
    body = response.json()

    cases = rows(db, "recovery_cases", merchant_id=MERCHANT_ID)
    assert len(cases) == 1
    case = cases[0]
    assert case["id"] == body["caseId"]
    assert case["playbook"] == "subscription_failure"
    assert case["amount_at_risk_cents"] == 299900
    assert case["status"] == "open"
    assert case["current_step"] == "detect"
    assert case["diagnosis"] is None

    events = rows(db, "events", merchant_id=MERCHANT_ID)
    assert len(events) == 1
    assert events[0]["event_type"] == "subscription.charged.failed"
    assert case["trigger_event_id"] == events[0]["id"]

    suresh = rows(db, "customers", external_id="cust_suresh_iyer")[0]
    assert case["customer_id"] == suresh["id"]


@pytest.mark.parametrize("code", SCRIPTED)
def test_fire_scenario_matches_its_metadata(
    code: str, loaded_client: TestClient, db: FakeSupabase
) -> None:
    """Every scripted scenario writes exactly what its catalogue entry promises."""
    meta = SCENARIO_METADATA[code]

    response = loaded_client.post(f"/api/simulator/scenarios/{code}")

    assert response.status_code == 200, response.text
    case = rows(db, "recovery_cases", id=response.json()["caseId"])[0]
    assert case["playbook"] == meta["playbook"]
    assert case["amount_at_risk_cents"] == meta["amount_at_risk_cents"]
    assert case["status"] == "open"

    event = rows(db, "events", id=case["trigger_event_id"])[0]
    assert event["event_type"] == meta["event_type"]
    assert event["payload"]["customer_id"] == meta["persona_external_id"]

    customer = rows(db, "customers", id=case["customer_id"])[0]
    assert customer["external_id"] == meta["persona_external_id"]


@pytest.mark.parametrize("code", SCRIPTED)
def test_fire_scenario_audits_as_system(
    code: str, loaded_client: TestClient, db: FakeSupabase
) -> None:
    loaded_client.post(f"/api/simulator/scenarios/{code}")

    audit = rows(db, "audit_events", merchant_id=MERCHANT_ID, event="scenario_fired")
    assert len(audit) == 1
    assert audit[0]["actor"] == "system"
    assert audit[0]["details"]["scenario_code"] == code
    assert audit[0]["trace_id"]


def test_fire_scenario_accepts_a_lowercase_code(loaded_client: TestClient) -> None:
    assert loaded_client.post("/api/simulator/scenarios/s2").status_code == 200


def test_fire_scenario_requires_fixtures(client: TestClient, db: FakeSupabase) -> None:
    response = client.post("/api/simulator/scenarios/S1")

    assert response.status_code == 424
    assert response.json()["error"]["message"] == "Load fixtures first"
    assert db.count("recovery_cases") == 0
    assert db.count("events") == 0


def test_fire_unknown_scenario_returns_400(loaded_client: TestClient) -> None:
    response = loaded_client.post("/api/simulator/scenarios/S9")

    assert response.status_code == 400
    assert "Unknown scenario" in response.json()["error"]["message"]


def test_fire_S1_twice_creates_two_cases(loaded_client: TestClient, db: FakeSupabase) -> None:
    first = loaded_client.post("/api/simulator/scenarios/S1").json()
    second = loaded_client.post("/api/simulator/scenarios/S1").json()

    assert first["caseId"] != second["caseId"]
    assert len(rows(db, "recovery_cases", merchant_id=MERCHANT_ID)) == 2
    assert len(rows(db, "events", merchant_id=MERCHANT_ID)) == 2
    # The customer is reused — a second failure is not a second customer.
    assert len(rows(db, "customers", external_id="cust_suresh_iyer")) == 1


def test_fire_B3_creates_eight_events(loaded_client: TestClient, db: FakeSupabase) -> None:
    response = loaded_client.post("/api/simulator/scenarios/B3")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["eventIds"]) == 8
    assert len(body["caseIds"]) == 8

    events = rows(db, "events", merchant_id=MERCHANT_ID)
    assert len(events) == 8
    assert {event["payload"]["bank"] for event in events} == {"SBI"}
    assert {event["payload"]["method"] for event in events} == {"upi"}


@pytest.mark.parametrize("code", ["B1", "B2"])
def test_batch_scenarios_are_accepted_but_write_nothing(
    code: str, loaded_client: TestClient, db: FakeSupabase
) -> None:
    response = loaded_client.post(f"/api/simulator/scenarios/{code}")

    assert response.status_code == 202
    assert "Phase 11" in response.json()["message"]
    assert db.count("recovery_cases") == 0
    assert db.count("events") == 0


def test_inject_reply_creates_customer_reply_row(
    loaded_client: TestClient, db: FakeSupabase
) -> None:
    case_id = loaded_client.post("/api/simulator/scenarios/S6").json()["caseId"]

    response = loaded_client.post(
        "/api/simulator/replies",
        json={"caseId": case_id, "channel": "whatsapp", "rawText": "STOP"},
    )

    assert response.status_code == 200, response.text
    replies = rows(db, "customer_replies", merchant_id=MERCHANT_ID)
    assert len(replies) == 1
    assert replies[0]["case_id"] == case_id
    assert replies[0]["raw_text"] == "STOP"
    assert replies[0]["channel"] == "whatsapp"
    assert replies[0]["id"] == response.json()["replyId"]

    audit = rows(db, "audit_events", merchant_id=MERCHANT_ID, event="reply_injected")
    assert audit and audit[0]["actor"] == "system"


def test_inject_reply_rejects_an_unknown_case(loaded_client: TestClient) -> None:
    response = loaded_client.post(
        "/api/simulator/replies",
        json={
            "caseId": "33333333-3333-4333-8333-333333333333",
            "channel": "sms",
            "rawText": "kal try karta hoon",
        },
    )

    assert response.status_code == 404


def test_inject_reply_rejects_an_unknown_channel(loaded_client: TestClient) -> None:
    case_id = loaded_client.post("/api/simulator/scenarios/S1").json()["caseId"]

    response = loaded_client.post(
        "/api/simulator/replies",
        json={"caseId": case_id, "channel": "pigeon", "rawText": "hi"},
    )

    assert response.status_code == 422


def test_status_tails_events_and_open_cases(loaded_client: TestClient) -> None:
    loaded_client.post("/api/simulator/scenarios/S1")
    loaded_client.post("/api/simulator/scenarios/S2")

    body = loaded_client.get("/api/simulator/status").json()

    assert body["fixturesLoaded"] is True
    assert len(body["recentEvents"]) == 2
    # Newest first — the panel reads top-down.
    assert body["recentEvents"][0]["eventType"] == "checkout.abandoned"
    assert body["recentEvents"][0]["customerName"] == "Priya Menon"
    assert len(body["inFlightCases"]) == 2


def test_status_caps_the_event_tail_at_twenty(loaded_client: TestClient) -> None:
    for _ in range(13):
        loaded_client.post("/api/simulator/scenarios/S3")
    loaded_client.post("/api/simulator/scenarios/B3")

    body = loaded_client.get("/api/simulator/status").json()

    assert len(body["recentEvents"]) == 20
