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
from app.agent.models import StepName
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
    # Phase 6's bandit now makes this choice, and the seeded priors for Sana's
    # context (SBI UPI, afternoon, no LTV yet) put `whatsapp_payment_link` well
    # ahead — which is the path scenarios.md scripts for S6. Phase 4 asserted a
    # silent retry here because the stub always played the conservative default.
    assert attempts[0]["action_type"] == "send_whatsapp"
    assert attempts[0]["adapter"] == "whatsapp_business_simulated"

    decision = rows_for(db, "agent_decisions", case_id)[0]
    assert decision["decision_source"] == "bandit"
    assert decision["bandit_chosen_arm"] == "whatsapp_payment_link"
    assert decision["bandit_context_vector"]["bank"] == "SBI"

    # A message is an attempt, not a recovery: the case has to stay open for
    # Sana's "STOP" to have something to stop.
    assert db.find_one("recovery_cases", case_id)["status"] == "in_flight"  # type: ignore[index]

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
    # The stronger property, and the one that matters: the guardrail *permitted*
    # this send — it is a message, not a retry, so no RBI spacing window applies,
    # and consent was still on record at check time — and the agent sent nothing
    # anyway, because it read Sana's unprocessed reply before acting on its own
    # decision. Compliance here comes from hearing first, not from happening to
    # be blocked.
    assert result.guardrail is not None
    assert result.guardrail.verdict == "PASS"
    assert result.guardrail.blocking_check is None
    assert result.listen is not None and result.listen.opt_out_signal is True
    assert StepName.EXECUTE not in result.steps_completed

    # Still exactly one attempt: the one from the first pass, before she replied.
    assert len(rows_for(db, "execution_attempts", case_id)) == 1

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
