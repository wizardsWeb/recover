"""The lift factors, held to the targets they were tuned for.

`arm_lift_factors` is the ground truth the simulation is built on, so a change
there moves every number the results screen shows. This file is what stops that
happening silently — it re-derives the rates and compares them against
`scenarios.md`.

Tolerances differ by metric on purpose. The overall rates aggregate a thousand
cases and are tight to three points. A per-playbook rate over the settled window
covers as few as twenty B2B cases and swings ten points run to run, so a
three-point assertion there would fail a third of the time and teach nothing
when it did. The loose bound is the honest one.
"""

import statistics

import pytest

from app.simulator.batch import BatchResult, run_batch

SEEDS = range(1, 13)

#: From `scenarios.md`, quoted for the converged policy.
TARGET_BANDIT = 0.38
TARGET_BASELINE = 0.22
TARGET_BY_PLAYBOOK = {
    "subscription_failure": 0.42,
    "checkout_abandonment": 0.31,
    "failed_payment": 0.38,
    "b2b_overdue": 0.28,
}


@pytest.fixture(scope="module")
def runs() -> list[BatchResult]:
    import asyncio

    async def go() -> list[BatchResult]:
        return [
            await run_batch(None, "m", n_cases=1000, seed=seed, persist_cases=False)
            for seed in SEEDS
        ]

    return asyncio.run(go())


def mean(runs: list[BatchResult], get: object) -> float:
    return statistics.mean(get(run) for run in runs)  # type: ignore[operator]


def test_the_settled_bandit_rate_hits_the_published_target(runs: list[BatchResult]) -> None:
    rate = mean(runs, lambda r: r.settled_recovery_rate_by_policy["bandit"])

    assert rate == pytest.approx(TARGET_BANDIT, abs=0.03)


def test_the_baseline_rate_hits_the_published_target(runs: list[BatchResult]) -> None:
    """The comparison is only worth making if the thing compared against is right.

    A baseline tuned too low would manufacture the lift the product claims.
    """
    rate = mean(runs, lambda r: r.settled_recovery_rate_by_policy["baseline"])

    assert rate == pytest.approx(TARGET_BASELINE, abs=0.03)


@pytest.mark.parametrize("playbook", sorted(TARGET_BY_PLAYBOOK))
def test_each_playbook_lands_near_its_target(runs: list[BatchResult], playbook: str) -> None:
    rate = mean(runs, lambda r: r.settled_recovery_rate_by_playbook.get(playbook, 0.0))

    assert rate == pytest.approx(TARGET_BY_PLAYBOOK[playbook], abs=0.08)


def test_the_bandit_wins_on_every_single_run(runs: list[BatchResult]) -> None:
    """Not on average — every time. A claim that holds on average and fails one
    demo in four is not a claim anybody should make on stage."""
    for run in runs:
        settled = run.settled_recovery_rate_by_policy
        assert settled["bandit"] > settled["baseline"]


def test_the_crossover_lands_where_the_chart_annotates_it(runs: list[BatchResult]) -> None:
    """The dashed line is drawn at this case number, so it has to be typical."""
    crossovers = sorted(run.bandit_convergence_case for run in runs)
    median = crossovers[len(crossovers) // 2]

    assert all(run.bandit_convergence_case > 0 for run in runs)
    assert 100 <= median <= 400


def test_roughly_sixty_percent_of_gross_is_genuinely_caused(runs: list[BatchResult]) -> None:
    """The attribution figure the results screen prints.

    It falls straight out of the self-heal rates, so an edit there that made the
    agent look better would show up here first.
    """
    share = mean(runs, lambda r: r.incremental_recovered_inr / r.gross_recovered_inr)

    assert share == pytest.approx(0.60, abs=0.06)


def test_a_thousand_cases_is_fast_enough_to_watch(runs: list[BatchResult]) -> None:
    """The simulation is in-memory; only the case rows touch the database."""
    assert mean(runs, lambda r: r.elapsed_seconds) < 2.0
