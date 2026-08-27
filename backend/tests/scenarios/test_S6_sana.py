"""S6 Sana, end to end — the compliance path.

This is the Phase 4 definition of done as one test. Fire the scenario, let the
agent work the case, have Sana reply "STOP", and assert that the agent hears it,
revokes consent across every channel, closes the case, and leaves a trail that
explains all of it.

It runs against the in-memory Supabase fake rather than a live project. The
alternative — a real Supabase test project — buys schema fidelity at the cost of
shared mutable state and a network round trip per assertion, and the thing under
test here is our own orchestration, not PostgREST. Schema fidelity is covered
where it belongs, by the migrations.

The second pass is the interesting half. By then the case is inside its RBI
retry-spacing window, so the guardrail blocks before EXECUTE — and the opt-out
must still be honoured. An agent that stops listening because it is not allowed
to speak is an agent that misses the one message it must never miss.
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
    """A client whose background agent runs against the same fake database.

    Unlike ``tests/simulator``, this suite *wants* the agent to run: the point is
    the whole path from fired scenario to revoked consent.
    """
    app.dependency_overrides[get_current_user_id] = lambda: MERCHANT_ID
    app.dependency_overrides[get_user_supabase] = lambda: db
    monkeypatch.setattr("app.api.simulator.get_service_client", lambda: db)
    monkeypatch.setattr("app.api.events.get_service_client", lambda: db)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def rows_for(db: FakeSupabase, table: str, case_id: str) -> list[dict[str, Any]]:
    return [row for row in db.rows(table) if row.get("case_id") == case_id]


async def test_s6_sana_full_flow(client: TestClient, db: FakeSupabase) -> None:
    assert client.post("/api/simulator/fixtures/load").status_code == 200

    # ── Fire S6 ────────────────────────────────────────────────────────
    fired = client.post("/api/simulator/scenarios/S6")
    assert fired.status_code == 200, fired.text
    case_id = fired.json()["caseId"]
    event_id = fired.json()["eventId"]

    case = db.find_one("recovery_cases", case_id)
    assert case is not None
    assert case["playbook"] == "failed_payment"
    assert case["amount_at_risk_cents"] == 68000

    # The agent ran on the fired event as a background task.
    attempts = rows_for(db, "execution_attempts", case_id)
    assert len(attempts) == 1
    # Phase 4's decide stub always plays the playbook's conservative default arm,
    # which for failed_payment is a silent retry. S6's catalogue entry names
    # `whatsapp_payment_link` as its expected path — that is the Phase 6 bandit's
    # choice, not this phase's, and asserting it here would be asserting a
    # behaviour no code in the repo has yet.
    assert attempts[0]["action_type"] == "retry_charge"
    assert attempts[0]["adapter"] == "razorpay_subscriptions_simulated"

    trail = [row["event"] for row in rows_for(db, "audit_events", case_id)]
    for step in (
        "detect:case_opened",
        "diagnose:diagnosis_complete",
        "uplift_check:uplift_verdict",
        "decide:decision_made",
        "guardrail:guardrail_pass",
        "execute:execution_attempted",
        "listen:reply_classified",
    ):
        assert step in trail, f"missing {step} in {trail}"

    assert db.find_one("recovery_cases", case_id)["status"] == "in_flight"  # type: ignore[index]

    # ── Sana replies STOP ──────────────────────────────────────────────
    injected = client.post(
        "/api/simulator/replies",
        json={"caseId": case_id, "channel": "whatsapp", "rawText": "STOP"},
    )
    assert injected.status_code == 200, injected.text

    # ── Second pass: the agent picks the reply up ──────────────────────
    result = await process_event(event_id, MERCHANT_ID, db)
    assert result is not None
    assert result.case_id == case_id
    # Blocked at the guardrail — a retry seconds after the last one is inside the
    # RBI spacing window — and the opt-out is honoured regardless.
    assert result.guardrail is not None
    assert result.guardrail.blocking_check == "rbi_min_hours_between_retries"
    assert result.listen is not None and result.listen.opt_out_signal is True

    sana = [c for c in db.rows("customers") if c["external_id"] == "cust_sana_khatri"][0]
    consent = sana["consent"]
    assert consent["opted_out_at"] is not None
    assert consent["whatsapp"] is False
    assert consent["sms"] is False
    assert consent["email"] is False

    closed_case = db.find_one("recovery_cases", case_id)
    assert closed_case is not None
    assert closed_case["status"] == "stopped"
    assert closed_case["closed_at"] is not None

    final_trail = [row["event"] for row in rows_for(db, "audit_events", case_id)]
    assert "listen:consent_revoked" in final_trail
    assert final_trail[-1] == "audit:case_closed"
    assert len(final_trail) >= 9

    # The closing reason is the customer's, not the machine's.
    closing = rows_for(db, "audit_events", case_id)[-1]
    assert "opted out" in closing["details"]["reason"]

    # The reply is marked handled, so a third pass cannot re-apply it.
    reply = rows_for(db, "customer_replies", case_id)[0]
    assert reply["applied_state_update"] == "REVOKE_CONSENT_ALL_CHANNELS"


async def test_s6_third_pass_does_not_re_revoke(client: TestClient, db: FakeSupabase) -> None:
    """Once consent is revoked, the guardrail refuses at check 1 and stays there."""
    client.post("/api/simulator/fixtures/load")
    fired = client.post("/api/simulator/scenarios/S6").json()
    client.post(
        "/api/simulator/replies",
        json={"caseId": fired["caseId"], "channel": "whatsapp", "rawText": "STOP"},
    )
    await process_event(fired["eventId"], MERCHANT_ID, db)

    before = len(rows_for(db, "audit_events", fired["caseId"]))
    result = await process_event(fired["eventId"], MERCHANT_ID, db)

    # The case is closed, so it is no longer an active case for this customer and
    # playbook — a fresh one opens rather than the closed one being reworked.
    assert result is not None
    assert result.case_id != fired["caseId"]
    assert result.guardrail is not None
    assert result.guardrail.blocking_check == "explicit_opt_out"
    assert len(rows_for(db, "audit_events", fired["caseId"])) == before
