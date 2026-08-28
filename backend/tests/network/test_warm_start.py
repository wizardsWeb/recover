"""Borrowing the network's view as a starting belief.

The danger with a prior is that it is indistinguishable from evidence once it
is inside the same numbers. These tests draw that line: what a warm start is
allowed to touch, when it is allowed to fire, and that it never reaches the
table the dashboard reads as "what this merchant learned".
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.agent.bandit.thompson import (
    NETWORK_PRIOR_STRENGTH,
    fetch_posteriors,
    update_posterior,
    warm_start_from_network,
)
from app.agent.playbooks import PLAYBOOK_CONFIGS
from tests.simulator.fake_supabase import FakeSupabase

MERCHANT = "11111111-1111-4111-8111-111111111111"
PLAYBOOK = "subscription_failure"
BUCKET = "SBI:UPI:morning:high"
ARMS = list(PLAYBOOK_CONFIGS[PLAYBOOK].arms)
CONTEXT: dict[str, Any] = {"bank": "SBI", "method": "upi", "hour_ist": 10}


def network(db: FakeSupabase, *, rate: float, bank: str = "SBI", method: str = "upi") -> None:
    now = datetime.now(UTC) - timedelta(hours=2)
    db.rows("network_stats").append(
        {
            "id": f"ns-{len(db.rows('network_stats'))}",
            "bank": bank,
            "method": method,
            "hour_of_day": 10,
            "day_of_week": 0,
            "success_rate": rate,
            "sample_size": 300,
            "window_start": now.isoformat(),
            "window_end": now.isoformat(),
        }
    )


def posterior(db: FakeSupabase, arm: str, *, alpha: float, beta: float, n: int) -> None:
    db.rows("bandit_posteriors").append(
        {
            "id": f"bp-{len(db.rows('bandit_posteriors'))}",
            "merchant_id": MERCHANT,
            "playbook": PLAYBOOK,
            "arm_name": arm,
            "context_bucket": BUCKET,
            "alpha": alpha,
            "beta": beta,
            "n_pulls": n,
        }
    )


def retry_arm() -> str:
    from app.agent.playbooks import ARM_TO_ACTION_TYPE

    return next(
        arm
        for arm in ARMS
        if ARM_TO_ACTION_TYPE.get(arm) is not None
        and ARM_TO_ACTION_TYPE[arm].value == "retry_charge"
    )


def message_arm() -> str:
    from app.agent.playbooks import ARM_TO_ACTION_TYPE

    return next(
        arm
        for arm in ARMS
        if ARM_TO_ACTION_TYPE.get(arm) is not None
        and ARM_TO_ACTION_TYPE[arm].value != "retry_charge"
    )


# ── What it says ───────────────────────────────────────────────────────


def test_a_healthy_bank_seeds_only_the_retry_arms() -> None:
    """The network measures a rail, not a message.

    Giving a WhatsApp arm a prior derived from UPI settlement rates would be
    inventing evidence about something nobody measured.
    """
    db = FakeSupabase()
    network(db, rate=0.85)

    priors = warm_start_from_network(db, ARMS, "SBI", "upi", 10)

    assert retry_arm() in priors
    assert message_arm() not in priors
    alpha, beta, n_pulls = priors[retry_arm()]
    assert alpha == pytest.approx(0.85 * NETWORK_PRIOR_STRENGTH)
    assert beta == pytest.approx(0.15 * NETWORK_PRIOR_STRENGTH)
    assert n_pulls == 0


def test_a_degraded_bank_also_nudges_the_arms_that_route_around_it() -> None:
    """The behaviour worth having: don't burn a retry on a rail that is failing."""
    db = FakeSupabase()
    network(db, rate=0.22)

    priors = warm_start_from_network(db, ARMS, "SBI", "upi", 10)

    retry_alpha = priors[retry_arm()][0]
    message_alpha = priors[message_arm()][0]
    assert message_alpha > retry_alpha


def test_the_prior_carries_no_pulls() -> None:
    """`n_pulls` is what separates a belief from an observation."""
    db = FakeSupabase()
    network(db, rate=0.8)

    assert all(
        pulls == 0 for _, _, pulls in warm_start_from_network(db, ARMS, "SBI", "upi", 10).values()
    )


def test_readings_are_weighted_by_sample_size() -> None:
    db = FakeSupabase()
    network(db, rate=0.9)
    db.rows("network_stats")[0]["sample_size"] = 900
    network(db, rate=0.3)
    db.rows("network_stats")[1]["sample_size"] = 100

    alpha, beta, _ = warm_start_from_network(db, ARMS, "SBI", "upi", 10)[retry_arm()]

    assert alpha / (alpha + beta) == pytest.approx((0.9 * 900 + 0.3 * 100) / 1000, abs=0.01)


def test_no_network_view_says_nothing() -> None:
    assert warm_start_from_network(FakeSupabase(), ARMS, "SBI", "upi", 10) == {}


def test_another_banks_readings_are_not_borrowed() -> None:
    db = FakeSupabase()
    network(db, rate=0.2, bank="HDFC", method="card")

    assert warm_start_from_network(db, ARMS, "SBI", "upi", 10) == {}


def test_an_unreachable_network_table_is_not_an_error() -> None:
    """A prior is a nicety; failing the decision over one is not."""

    class Broken:
        def table(self, name: str) -> Any:
            raise ConnectionError("supabase unavailable")

    assert warm_start_from_network(Broken(), ARMS, "SBI", "upi", 10) == {}


# ── When it fires ──────────────────────────────────────────────────────


async def test_an_unplayed_bucket_warm_starts() -> None:
    db = FakeSupabase()
    network(db, rate=0.85)

    result = await fetch_posteriors(db, MERCHANT, PLAYBOOK, BUCKET, ARMS, context=CONTEXT)

    assert retry_arm() in result


async def test_learned_posteriors_are_never_overridden() -> None:
    """The hard constraint.

    A bucket with a single played arm has real evidence in it. Mixing a
    borrowed prior into the other seven would have the bandit compare what it
    learned against what it assumed, and prefer whichever the network happened
    to flatter.
    """
    db = FakeSupabase()
    network(db, rate=0.95)
    posterior(db, retry_arm(), alpha=2.0, beta=18.0, n=20)

    result = await fetch_posteriors(db, MERCHANT, PLAYBOOK, BUCKET, ARMS, context=CONTEXT)

    assert result == {retry_arm(): (2.0, 18.0, 20)}


async def test_without_context_the_behaviour_is_unchanged() -> None:
    """Every pre-Phase-10 caller keeps the flat prior it had."""
    db = FakeSupabase()
    network(db, rate=0.85)

    assert await fetch_posteriors(db, MERCHANT, PLAYBOOK, BUCKET, ARMS) == {}


async def test_the_reward_path_never_warm_starts() -> None:
    """The failure that would launder a prior into evidence.

    `update_posterior` reads the current posterior, adds one observation, and
    writes the sum back. Warm-starting that read would persist a borrowed
    belief into `bandit_posteriors` as though the merchant had learned it.
    """
    db = FakeSupabase()
    network(db, rate=0.95)

    await update_posterior(db, MERCHANT, PLAYBOOK, retry_arm(), BUCKET, reward=1.0)

    written = db.rows("bandit_posteriors")[0]
    # Beta(1,1) plus one win — not Beta(9.5, 0.5) plus one.
    assert float(written["alpha"]) == 2.0
    assert float(written["beta"]) == 1.0
    assert written["n_pulls"] == 1


async def test_a_warm_start_is_not_written_to_the_posteriors_table() -> None:
    """It must never appear on the dashboard as something the merchant learned."""
    db = FakeSupabase()
    network(db, rate=0.85)

    await fetch_posteriors(db, MERCHANT, PLAYBOOK, BUCKET, ARMS, context=CONTEXT)

    assert db.rows("bandit_posteriors") == []


async def test_an_incomplete_context_falls_back_rather_than_guessing() -> None:
    db = FakeSupabase()
    network(db, rate=0.85)

    assert (
        await fetch_posteriors(db, MERCHANT, PLAYBOOK, BUCKET, ARMS, context={"bank": "SBI"}) == {}
    )
