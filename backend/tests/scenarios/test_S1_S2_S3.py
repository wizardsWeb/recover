"""S1, S2 and S3 end to end — the bandit choosing the scripted arm.

Phase 6's claim is that seeded priors make the agent pick the right arm for the
right reason, and that the outcome flows back into the posterior it came from.
These tests check both halves against the real loop: fixtures loaded through the
API, the scenario fired, the agent run, then the database read back.

What each scenario is here to prove is different, and that is the point of
having three:

* **S1** — the money moves. A retry succeeds, the case closes as recovered, and
  the arm's alpha goes up by exactly one.
* **S2** — a discount arm wins on evidence, not on nerve. The bandit picks 8%
  over both 12% and no discount, and the case stays open awaiting a reply.
* **S3** — the best action is silence. Nothing is sent at 11:34pm on a Saturday,
  which is the one outcome a recovery product is least inclined to produce.

``tests/scenarios/conftest.py`` pins the clock and makes the Thompson draw
deterministic; without both, the arm and the guardrail verdict would change from
run to run.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

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


def posterior(db: FakeSupabase, playbook: str, arm: str, bucket: str) -> dict[str, Any] | None:
    return next(
        (
            row
            for row in db.rows("bandit_posteriors")
            if row["playbook"] == playbook
            and row["arm_name"] == arm
            and row["context_bucket"] == bucket
        ),
        None,
    )


def load(client: TestClient) -> None:
    """Load the personas and the demo priors, and confirm the priors went in."""
    loaded = client.post("/api/simulator/fixtures/load")
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["loaded"]["banditPriorsSeeded"] is True


def fire(client: TestClient, code: str) -> dict[str, Any]:
    """Load, then fire one scenario and run the agent over it."""
    load(client)
    fired = client.post(f"/api/simulator/scenarios/{code}")
    assert fired.status_code == 200, fired.text
    return dict(fired.json())


# ── S1 — Suresh: the salary-cycle save ─────────────────────────────────


async def test_s1_picks_the_inferred_date_retry_and_records_the_recovery(
    client: TestClient, db: FakeSupabase
) -> None:
    bucket = "ICIC:UPI:morning:high"
    arm = "retry_at_inferred_date_plus_whatsapp_fallback"

    assert posterior(db, "subscription_failure", arm, bucket) is None

    # Read the prior *before* firing. The pass posts a reward on close, so after
    # the scenario runs this row is already one observation further on — which is
    # exactly what the end of this test asserts.
    load(client)
    seeded = posterior(db, "subscription_failure", arm, bucket)
    assert seeded is not None and seeded["alpha"] == 18.0

    fired = client.post("/api/simulator/scenarios/S1")
    assert fired.status_code == 200, fired.text
    case_id = fired.json()["caseId"]

    decision = rows_for(db, "agent_decisions", case_id)[0]
    assert decision["decision_source"] == "bandit"
    assert decision["bandit_chosen_arm"] == arm
    assert decision["bandit_mode"] == "exploit"
    assert decision["bandit_context_vector"]["bank"] == "ICIC"
    assert decision["bandit_context_vector"]["has_salary_mismatch_pattern"] is True

    # A retry is the one action that actually moves money, so this case closes.
    attempts = rows_for(db, "execution_attempts", case_id)
    assert len(attempts) == 1
    assert attempts[0]["action_type"] == "retry_charge"

    case = db.find_one("recovery_cases", case_id)
    assert case is not None
    assert case["status"] == "recovered"
    assert case["amount_recovered_cents"] == 299900
    assert case["closed_at"] is not None

    # The outcome landed on the posterior the draw came from: 18 -> 19.
    after = posterior(db, "subscription_failure", arm, bucket)
    assert after is not None
    assert after["alpha"] == 19.0
    assert after["beta"] == 4.0

    reward = [r for r in db.rows("bandit_rewards") if r["case_id"] == case_id]
    assert len(reward) == 1
    assert reward[0]["context_bucket"] == bucket
    assert float(reward[0]["reward_value"]) == 1.0


# ── S2 — Priya: 8% beats both 12% and nothing ──────────────────────────


async def test_s2_picks_the_eight_percent_cart_and_stays_open(
    client: TestClient, db: FakeSupabase
) -> None:
    fired = fire(client, "S2")
    case_id = fired["caseId"]

    decision = rows_for(db, "agent_decisions", case_id)[0]
    assert decision["bandit_chosen_arm"] == "whatsapp_saved_cart_8pct"
    assert decision["decision_source"] == "bandit"
    assert decision["action_params"]["discount_pct"] == 8

    # The counterfactual a merchant asking "why discount at all?" needs: 12% is
    # ranked, and it lost on evidence rather than on being left out.
    alternatives = {alt["arm_name"]: alt for alt in decision["bandit_alternatives"]}
    assert alternatives["whatsapp_saved_cart_12pct"]["chosen"] is False
    assert (
        alternatives["whatsapp_saved_cart_8pct"]["expected_reward"]
        > alternatives["whatsapp_saved_cart_12pct"]["expected_reward"]
    )
    assert alternatives["whatsapp_saved_cart_no_discount"]["not_chosen_reason"]

    attempts = rows_for(db, "execution_attempts", case_id)
    assert attempts[0]["action_type"] == "send_whatsapp"

    # A message is an attempt, not a recovery — nothing has come back yet.
    case = db.find_one("recovery_cases", case_id)
    assert case is not None
    assert case["status"] == "in_flight"
    assert case["amount_recovered_cents"] == 0
    assert db.rows("bandit_rewards") == []


# ── S3 — Aditya: the best move is to say nothing ───────────────────────


async def test_s3_retries_silently_and_sends_no_message(
    client: TestClient, db: FakeSupabase
) -> None:
    fired = fire(client, "S3")
    case_id = fired["caseId"]

    decision = rows_for(db, "agent_decisions", case_id)[0]
    assert decision["bandit_chosen_arm"] == "silent_retry_next_morning"
    assert decision["bandit_context_vector"]["period"] == "night"

    attempts = rows_for(db, "execution_attempts", case_id)
    assert len(attempts) == 1
    assert attempts[0]["action_type"] == "retry_charge"
    # The assertion S3 exists for: no customer-facing action of any kind.
    assert not [a for a in attempts if str(a["action_type"]).startswith("send_")]


async def test_s3_reward_lands_in_the_night_bucket_not_the_morning_one(
    client: TestClient, db: FakeSupabase
) -> None:
    """Context isolation, checked where it would actually go wrong.

    The reward is credited from the vector stored at decide time. If it were
    recomputed at close time — hours later, in the morning — it would teach the
    morning bucket a lesson the night bucket learned.
    """
    fire(client, "S3")

    night = posterior(db, "failed_payment", "silent_retry_next_morning", "HDFC:CAR:night:low")
    morning = posterior(db, "failed_payment", "silent_retry_next_morning", "HDFC:CAR:morning:low")

    assert night is not None and night["alpha"] == 19.0  # seeded 18, +1 for the recovery
    assert morning is None
