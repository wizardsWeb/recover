"""Thompson Sampling, tested as a distribution rather than as a return value.

A randomised policy has no single correct output, so these assert on *rates over
many draws*. That makes the thresholds a design decision: each one is set wide
enough that a correct implementation effectively never trips it, and tight
enough that a broken one always does. A test that fails once a month is worse
than no test, and a test that passes for a broken sampler is worse still.

This module deliberately does **not** use the ``deterministic_bandit`` fixture
that the loop and scenario tests rely on. The randomness is the subject here.
"""

import pytest

from app.agent.bandit.thompson import (
    COLD_START_MASS,
    ArmSample,
    fetch_posteriors,
    is_exploring,
    run_thompson_sampling,
    sample_beta,
    update_posterior,
)
from tests.simulator.fake_supabase import FakeSupabase

MERCHANT_ID = "11111111-1111-4111-8111-111111111111"
DRAWS = 1000


def test_every_arm_comes_back_ranked_by_its_draw() -> None:
    arms = ["a", "b", "c", "d"]
    ranked = run_thompson_sampling(arms, {})

    # Every arm comes back — the losers are the counterfactual the case detail
    # page renders, so dropping them would make the decision unexplainable.
    assert {s.arm_name for s in ranked} == set(arms)
    thetas = [s.sampled_theta for s in ranked]
    assert thetas == sorted(thetas, reverse=True)


def test_a_well_evidenced_arm_almost_always_wins() -> None:
    """Beta(50,2) against Beta(2,50) is not a close call, and must not behave like one."""
    wins = sum(
        1
        for _ in range(DRAWS)
        if run_thompson_sampling(
            ["strong", "weak"], {"strong": (50.0, 2.0, 52), "weak": (2.0, 50.0, 52)}
        )[0].arm_name
        == "strong"
    )
    assert wins > DRAWS * 0.9, f"strong arm won only {wins}/{DRAWS}"


def test_cold_start_is_a_coin_flip() -> None:
    """With no evidence the policy must not have a favourite.

    A sampler that quietly preferred the first arm in the list would look fine
    in every other test — the winner would still be a valid arm — and would
    silently stop exploring in production.
    """
    wins = sum(
        1
        for _ in range(DRAWS)
        if run_thompson_sampling(["arm_a", "arm_b"], {})[0].arm_name == "arm_a"
    )
    assert 350 < wins < 650, f"arm_a won {wins}/{DRAWS} — not a fair split"


@pytest.mark.parametrize("alpha,beta", [(0.0, 0.0), (-1.0, 5.0), (5.0, -1.0), (0.0, 3.0)])
def test_unusable_parameters_degrade_to_a_coin_flip(alpha: float, beta: float) -> None:
    """A corrupt posterior must not take down a decision."""
    assert sample_beta(alpha, beta) == 0.5


def test_missing_arms_take_the_flat_prior() -> None:
    """A newly added arm has to be competitive, not invisible."""
    ranked = run_thompson_sampling(["known", "brand_new"], {"known": (10.0, 5.0, 13)})
    fresh = next(s for s in ranked if s.arm_name == "brand_new")

    assert (fresh.alpha, fresh.beta) == (1.0, 1.0)
    assert fresh.expected_win_rate == 0.5
    assert fresh.is_cold is True
    assert fresh.alpha + fresh.beta <= COLD_START_MASS


def test_exploring_is_true_only_when_the_draw_overrules_the_evidence() -> None:
    better = ArmSample("better", 0.4, 9.0, 1.0, 8, 0.9, False)
    worse = ArmSample("worse", 0.8, 1.0, 9.0, 8, 0.1, False)

    # The worse arm drew higher — this pull bought information.
    assert is_exploring(worse, better) is True
    assert is_exploring(better, worse) is False
    # One arm on the table means there was no alternative to forgo.
    assert is_exploring(better, None) is False


async def test_a_success_moves_alpha_and_a_failure_moves_beta() -> None:
    db = FakeSupabase()

    await update_posterior(
        db, MERCHANT_ID, "failed_payment", "retry_now", "HDFC:CAR:night:low", 1.0
    )
    after_win = await fetch_posteriors(
        db, MERCHANT_ID, "failed_payment", "HDFC:CAR:night:low", ["retry_now"]
    )
    # First observation lands on the flat prior: Beta(1,1) -> Beta(2,1).
    assert after_win["retry_now"] == (2.0, 1.0, 1)

    await update_posterior(
        db, MERCHANT_ID, "failed_payment", "retry_now", "HDFC:CAR:night:low", 0.0
    )
    after_loss = await fetch_posteriors(
        db, MERCHANT_ID, "failed_payment", "HDFC:CAR:night:low", ["retry_now"]
    )
    assert after_loss["retry_now"] == (2.0, 2.0, 2)
    # Updated in place, not appended — the posterior is a summary, not a log.
    assert len(db.rows("bandit_posteriors")) == 1


async def test_posteriors_do_not_leak_across_context_buckets() -> None:
    """The whole point of bucketing: night evidence must not teach the morning."""
    db = FakeSupabase()

    await update_posterior(
        db, MERCHANT_ID, "failed_payment", "retry_now", "HDFC:CAR:night:low", 1.0
    )
    morning = await fetch_posteriors(
        db, MERCHANT_ID, "failed_payment", "HDFC:CAR:morning:low", ["retry_now"]
    )

    assert morning == {}


async def test_a_dead_table_reads_as_no_evidence() -> None:
    """A statistics table being down must cost exploration, not the decision."""

    class _DeadSupabase:
        def table(self, _name: str) -> object:
            raise RuntimeError("connection refused")

    result = await fetch_posteriors(_DeadSupabase(), MERCHANT_ID, "failed_payment", "b", ["a"])
    assert result == {}


async def test_update_never_raises_on_a_dead_table() -> None:
    class _DeadSupabase:
        def table(self, _name: str) -> object:
            raise RuntimeError("connection refused")

    # No assertion beyond "it returned": learning must never break a closed case.
    await update_posterior(_DeadSupabase(), MERCHANT_ID, "failed_payment", "a", "b", 1.0)
