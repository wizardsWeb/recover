"""The posterior update, and why it moved into Postgres.

The old implementation read alpha and beta, added one, and wrote both back. Two
cases closing in the same instant both read the same alpha and both write the
same alpha+1, so one observation is lost — silently, and in proportion to how
busy the merchant is. These tests pin the new path and the fallback that covers
a project where the migration has not been applied.
"""

from typing import Any

import pytest

from app.agent.bandit.thompson import update_posterior
from tests.simulator.conftest import MERCHANT_ID
from tests.simulator.fake_supabase import FakeSupabase

PLAYBOOK = "subscription_failure"
ARM = "retry_at_inferred_date"
BUCKET = "ICICI:UPI:morning:high"


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    fake.seed_merchant(MERCHANT_ID)
    return fake


def posterior(db: FakeSupabase) -> dict[str, Any] | None:
    return next((r for r in db.rows("bandit_posteriors") if r.get("arm_name") == ARM), None)


@pytest.mark.asyncio
async def test_first_success_lands_on_beta_2_1(db: FakeSupabase) -> None:
    """An arm with no row starts from the flat prior plus this observation."""
    await update_posterior(db, MERCHANT_ID, PLAYBOOK, ARM, BUCKET, reward=1.0)

    row = posterior(db)
    assert row is not None
    assert (row["alpha"], row["beta"], row["n_pulls"]) == (2.0, 1.0, 1)


@pytest.mark.asyncio
async def test_first_failure_lands_on_beta_1_2(db: FakeSupabase) -> None:
    await update_posterior(db, MERCHANT_ID, PLAYBOOK, ARM, BUCKET, reward=0.0)

    row = posterior(db)
    assert row is not None
    assert (row["alpha"], row["beta"], row["n_pulls"]) == (1.0, 2.0, 1)


@pytest.mark.asyncio
async def test_observations_accumulate_on_one_row(db: FakeSupabase) -> None:
    for reward in (1.0, 1.0, 0.0, 1.0):
        await update_posterior(db, MERCHANT_ID, PLAYBOOK, ARM, BUCKET, reward=reward)

    row = posterior(db)
    assert row is not None
    assert (row["alpha"], row["beta"], row["n_pulls"]) == (4.0, 2.0, 4)
    assert len(db.rows("bandit_posteriors")) == 1


@pytest.mark.asyncio
async def test_sequential_updates_lose_nothing(db: FakeSupabase) -> None:
    """Twenty observations must produce twenty pulls.

    The single-threaded fake cannot reproduce the race the migration fixes — that
    is a Postgres guarantee — but it does catch the arithmetic bug the old code
    would have shown here if the increment were computed from a stale read.
    """
    for _ in range(20):
        await update_posterior(db, MERCHANT_ID, PLAYBOOK, ARM, BUCKET, reward=1.0)

    row = posterior(db)
    assert row is not None
    assert row["n_pulls"] == 20
    assert row["alpha"] == 21.0


@pytest.mark.asyncio
async def test_bucket_and_arm_are_separate_posteriors(db: FakeSupabase) -> None:
    await update_posterior(db, MERCHANT_ID, PLAYBOOK, ARM, BUCKET, reward=1.0)
    await update_posterior(db, MERCHANT_ID, PLAYBOOK, ARM, "HDFC:CARD:night:low", reward=0.0)
    await update_posterior(db, MERCHANT_ID, PLAYBOOK, "other_arm", BUCKET, reward=1.0)

    assert len(db.rows("bandit_posteriors")) == 3


@pytest.mark.asyncio
async def test_falls_back_when_the_migration_is_missing(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project without the function must still learn, loudly rather than not.

    An RPC-only implementation would stop the bandit dead and silently on any
    deployment where the migration had not been applied — a demo that looks fine
    and never converges.
    """

    def no_such_function(*_: Any, **__: Any) -> Any:
        raise RuntimeError('function public.increment_bandit_posterior does not exist')

    monkeypatch.setattr(db, "rpc", no_such_function)

    await update_posterior(db, MERCHANT_ID, PLAYBOOK, ARM, BUCKET, reward=1.0)

    row = posterior(db)
    assert row is not None
    assert (row["alpha"], row["beta"], row["n_pulls"]) == (2.0, 1.0, 1)


@pytest.mark.asyncio
async def test_a_dead_database_does_not_raise(
    db: FakeSupabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reward posting runs after the case has closed; its useful work is done."""

    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("connection reset")

    monkeypatch.setattr(db, "rpc", boom)
    monkeypatch.setattr(db, "table", boom)

    await update_posterior(db, MERCHANT_ID, PLAYBOOK, ARM, BUCKET, reward=1.0)
