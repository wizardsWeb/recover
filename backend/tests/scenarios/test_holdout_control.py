"""A control case, end to end.

The claim Phase 9 rests on is that holdout cases are genuinely untouched. That
is not something the uplift model can check — it consumes the group and trusts
it. So it is checked here, against the real loop: fire a scenario with the draw
pinned under the rate, and assert that nothing was sent, nothing was decided,
and nothing was learned.

Every one of these failures would be silent. The case would close, the ROI page
would show a number, and the number would overstate what the agent caused.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.agent import holdout
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


@pytest.fixture
def always_holdout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the draw below the rate.

    Overrides the suite-wide `no_holdout_by_default`. The threshold comparison
    in `should_hold_out` still runs for real — only the dice are loaded.
    """
    monkeypatch.setattr(holdout, "draw", lambda: 0.0)


def rows_for(db: FakeSupabase, table: str, case_id: str) -> list[dict[str, Any]]:
    return [row for row in db.rows(table) if row.get("case_id") == case_id]


def fire(client: TestClient, code: str) -> str:
    loaded = client.post("/api/simulator/fixtures/load")
    assert loaded.status_code == 200, loaded.text
    fired = client.post(f"/api/simulator/scenarios/{code}")
    assert fired.status_code == 200, fired.text
    return str(fired.json()["caseId"])


def test_a_control_case_is_never_contacted(
    client: TestClient, db: FakeSupabase, always_holdout: None
) -> None:
    case_id = fire(client, "S1")

    case = db.find_one("recovery_cases", case_id)
    assert case is not None
    assert case["is_holdout"] is True
    assert case["status"] == "holdout"

    # The whole point: no action of any kind reached the customer, and no
    # money was attributed to an agent that did nothing.
    assert rows_for(db, "execution_attempts", case_id) == []
    assert case["amount_recovered_cents"] == 0


def test_a_control_case_makes_no_decision(
    client: TestClient, db: FakeSupabase, always_holdout: None
) -> None:
    """No arm is pulled, so there is nothing for a reward to attach to later."""
    case_id = fire(client, "S1")

    assert rows_for(db, "agent_decisions", case_id) == []
    assert db.rows("bandit_rewards") == []


def test_a_control_case_does_not_move_the_bandit(
    client: TestClient, db: FakeSupabase, always_holdout: None
) -> None:
    """The seeded prior is untouched.

    A control that taught the bandit would be a control that changed the policy
    it is supposed to be measuring against.
    """
    client.post("/api/simulator/fixtures/load")
    before = [dict(row) for row in db.rows("bandit_posteriors")]

    client.post("/api/simulator/scenarios/S1")

    after = [dict(row) for row in db.rows("bandit_posteriors")]
    assert [(r["arm_name"], r["alpha"], r["beta"]) for r in before] == [
        (r["arm_name"], r["alpha"], r["beta"]) for r in after
    ]


def test_the_holdout_row_records_the_frozen_context(
    client: TestClient, db: FakeSupabase, always_holdout: None
) -> None:
    case_id = fire(client, "S1")

    holdouts = [row for row in db.rows("uplift_holdouts") if row["case_id"] == case_id]
    assert len(holdouts) == 1
    features = holdouts[0]["context_features"]

    # S1's context, captured at assignment rather than recomputed at train time.
    assert features["bank"] == "ICIC"
    assert features["period"] == "morning"
    assert holdouts[0]["outcome"] is None
    assert holdouts[0]["used_in_training"] is False


def test_the_audit_trail_says_why_nothing_happened(
    client: TestClient, db: FakeSupabase, always_holdout: None
) -> None:
    """A silent case with no explanation is indistinguishable from a broken one."""
    case_id = fire(client, "S1")

    events = [row["event"] for row in rows_for(db, "audit_events", case_id)]
    assert "detect:assigned_to_holdout" in events


def test_resolving_a_holdout_records_the_counterfactual_outcome(
    client: TestClient, db: FakeSupabase, always_holdout: None
) -> None:
    case_id = fire(client, "S1")

    resolved = client.post(
        "/api/simulator/holdout/resolve",
        json={"caseId": case_id, "outcome": "recovered", "amountCents": 299900},
    )
    assert resolved.status_code == 200, resolved.text

    row = next(r for r in db.rows("uplift_holdouts") if r["case_id"] == case_id)
    assert row["outcome"] == "recovered"
    assert row["outcome_amount_cents"] == 299900

    # The case row carries it too — the ROI comparison reads recovery from
    # recovery_cases for both groups, so a control that recovered has to show it.
    case = db.find_one("recovery_cases", case_id)
    assert case is not None
    assert case["amount_recovered_cents"] == 299900


def test_resolving_a_case_that_is_not_a_control_is_refused(
    client: TestClient, db: FakeSupabase
) -> None:
    """Treated cases have observed outcomes; stating one would be fabrication."""
    case_id = fire(client, "S1")

    refused = client.post(
        "/api/simulator/holdout/resolve",
        json={"caseId": case_id, "outcome": "recovered", "amountCents": 1000},
    )
    assert refused.status_code == 404
