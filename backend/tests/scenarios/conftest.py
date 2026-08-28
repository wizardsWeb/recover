"""Fixtures shared by the end-to-end scenario tests.

Two sources of non-determinism have to be pinned before a scenario test means
anything, and both are autouse because forgetting either produces a test that
passes on the developer's machine and fails in CI at 2am.

**The bandit.** DECIDE now draws from Beta posteriors, so the arm — and with it
the action type, the guardrail checks that apply, and the adapter that runs —
changes from run to run. ``sample_beta`` is replaced with the posterior mean, so
the winner is a function of the seeded data. With no posteriors seeded every arm
ties at the flat prior and ``sorted`` resolves the tie to the playbook's arm
order, which is stable.

**The clock.** Half the guardrail reads the wall clock: TRAI quiet hours block
messages between 21:00 and 09:00 IST, so a suite run late at night takes a
different path through the loop than the same suite at noon. The clock is pinned
to 10:30 IST *today* rather than to a fixed calendar date — a fixed date would
put every freshly-opened case weeks in the past and trip the playbook hard stop,
which is the opposite of the intended effect.
"""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.agent import guardrail as guardrail_module

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture(autouse=True)
def pinned_business_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the guardrail's clock to 10:30 IST today — outside quiet hours."""
    when = datetime.now(IST).replace(hour=10, minute=30, second=0, microsecond=0)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            return when.astimezone(tz) if tz else when.replace(tzinfo=None)

    monkeypatch.setattr(guardrail_module, "datetime", _Frozen)


@pytest.fixture(autouse=True)
def deterministic_bandit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the Thompson draw with the posterior mean.

    Keeps the whole selection path under test — fetch, rank, explore/exploit
    label, alternatives — while making the chosen arm depend on the seeded
    priors rather than on the random seed.
    """
    from app.agent.bandit import thompson

    def _mean(alpha: float, beta: float) -> float:
        mass = alpha + beta
        return (alpha / mass) if mass > 0 else 0.5

    monkeypatch.setattr(thompson, "sample_beta", _mean)


@pytest.fixture(autouse=True)
def offline_dag_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep fixture loading from reaching for a real Supabase client.

    Loading publishes the causal graph, which is global reference data and so
    goes through the service role. Unpatched, that builds a live client against
    the stub URL in `tests/conftest.py` and waits for it to fail — swallowed by
    the loader, so the symptom is a slow suite rather than an error.

    The seeding itself is covered directly in `tests/agent/test_causal_dag_seed`.
    """
    from app.simulator import loader

    monkeypatch.setattr(loader, "seed_causal_dag", lambda _: {"nodes": 0})
