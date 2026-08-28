"""The dual-policy batch runner.

A simulator that is wrong does not fail — it draws a smooth curve and the demo
lands. So these tests are about the ways a convincing curve can be a lie: a
comparison that is not like-for-like, money counted twice, a bandit that
learned from the baseline's outcomes, or a run that quietly wrote its invented
posteriors back into the table that drives real decisions.
"""

import asyncio
from typing import Any

import pytest

from app.agent.playbooks import PLAYBOOK_CONFIGS
from app.simulator import batch as module
from app.simulator.batch import (
    SYNTHETIC_FLAG,
    BatchCase,
    ComplianceSummary,
    _aggregate,
    _convergence_window,
    run_batch,
)
from tests.simulator.fake_supabase import FakeSupabase

MERCHANT = "11111111-1111-4111-8111-111111111111"


async def small(**kwargs: Any) -> Any:
    defaults: dict[str, Any] = {"n_cases": 200, "seed": 5, "persist_cases": False}
    defaults.update(kwargs)
    return await run_batch(None, MERCHANT, **defaults)


# ── The comparison is like-for-like ────────────────────────────────────


async def test_both_policies_play_the_same_customers() -> None:
    """Otherwise the gap between the lines is confounded with who landed where.

    Same case id on both sides means the same drawn amount, the same
    willingness to pay, and the same guardrail state — so the only thing left
    to explain a difference is the arm.
    """
    result = await small()

    assert result.total_cases == 200
    assert result.recovery_rate_by_policy.keys() == {"bandit", "baseline"}


async def test_the_baseline_only_ever_plays_its_playbook_default() -> None:
    """A baseline that varied would be a second bandit, and prove nothing."""
    cases: list[BatchCase] = []
    original = module._play

    def capture(world: Any, arm: str, policy: str, case_id: str) -> BatchCase:
        played = original(world, arm, policy, case_id)
        cases.append(played)
        return played

    module._play = capture
    try:
        await small()
    finally:
        module._play = original

    for case in cases:
        if case.policy == "baseline":
            assert case.arm_chosen == PLAYBOOK_CONFIGS[case.playbook].default_arm


async def test_the_bandit_beats_the_baseline_by_the_end() -> None:
    """The claim the whole feature exists to support."""
    result = await run_batch(None, MERCHANT, n_cases=1000, seed=3, persist_cases=False)

    assert (
        result.settled_recovery_rate_by_policy["bandit"]
        > result.settled_recovery_rate_by_policy["baseline"]
    )


async def test_exploration_is_paid_for_rather_than_hidden() -> None:
    """The whole-run rate must sit below the settled one.

    If it did not, the bandit would have been ahead from its first case and the
    learning curve would be a straight line — which would mean the lift factors
    made a random arm better than the rule, not that the algorithm worked.
    """
    result = await run_batch(None, MERCHANT, n_cases=1000, seed=3, persist_cases=False)

    assert (
        result.recovery_rate_by_policy["bandit"] < result.settled_recovery_rate_by_policy["bandit"]
    )


# ── The bandit learns, and only from itself ────────────────────────────


async def test_only_the_bandits_own_outcomes_move_its_posteriors() -> None:
    """Feeding it the baseline's results too would double its evidence."""
    updates: list[tuple[str, bool]] = []
    original = module._Posteriors.update

    def capture(self: Any, playbook: str, bucket: str, arm: str, recovered: bool) -> None:
        updates.append((arm, recovered))
        original(self, playbook, bucket, arm, recovered)

    module._Posteriors.update = capture
    try:
        result = await small()
    finally:
        module._Posteriors.update = original

    assert len(updates) == result.total_cases


async def test_the_run_never_writes_to_bandit_posteriors() -> None:
    """The constraint that keeps a simulation out of the live policy.

    Outcomes here are drawn from numbers somebody made up. Persisting them would
    let a demo permanently steer the bandit that handles real money, and the
    resulting rows would be indistinguishable on the dashboard from evidence the
    merchant actually paid for.
    """
    db = FakeSupabase()
    db.seed_merchant(MERCHANT)

    await run_batch(db, MERCHANT, n_cases=100, seed=1, persist_cases=False)

    assert db.rows("bandit_posteriors") == []


async def test_a_run_starts_from_what_the_merchant_already_learned() -> None:
    db = FakeSupabase()
    db.rows("bandit_posteriors").append(
        {
            "merchant_id": MERCHANT,
            "playbook": "failed_payment",
            "arm_name": "retry_now",
            "context_bucket": "HDFC:UPI:morning:med",
            "alpha": 40.0,
            "beta": 2.0,
            "n_pulls": 42,
        }
    )

    posteriors = module._Posteriors()
    posteriors.seed(db.rows("bandit_posteriors"))

    loaded = posteriors.for_bucket("failed_payment", "HDFC:UPI:morning:med", ["retry_now"])
    assert loaded["retry_now"] == (40.0, 2.0, 42)


async def test_an_unreadable_posterior_row_does_not_stop_the_run() -> None:
    posteriors = module._Posteriors()
    posteriors.seed([{"playbook": "failed_payment"}, {"alpha": "not a number"}])

    assert posteriors.for_bucket("failed_payment", "any", ["retry_now"]) == {}


# ── Money ──────────────────────────────────────────────────────────────


def case(policy: str, *, recovered: bool, amount: float = 1000.0) -> BatchCase:
    return BatchCase(
        case_id="c",
        playbook="failed_payment",
        context_bucket="b",
        arm_chosen="retry_now",
        policy=policy,
        recovered=recovered,
        amount_inr=amount,
        days_to_recovery=1.0,
        intervention_cost_inr=0.35,
    )


def test_money_is_counted_once_not_once_per_policy() -> None:
    """Both policies played every customer.

    Summing across them would double every rupee and report a recovery rate
    over a population twice its real size.
    """
    cases = [case("bandit", recovered=True), case("baseline", recovered=True)]

    result = _aggregate(cases, [], ComplianceSummary())

    assert result.total_cases == 1
    assert result.gross_recovered_inr == 1000.0
    assert result.total_at_risk_inr == 1000.0


def test_incremental_subtracts_what_would_have_arrived_anyway() -> None:
    """Gross counts every rupee that landed; only the gap was caused."""
    cases = [case("bandit", recovered=True) for _ in range(10)]

    result = _aggregate(cases, [], ComplianceSummary())

    assert result.gross_recovered_inr == 10_000.0
    # failed_payment self-heals 16% of the time, so 1,600 of that arrived
    # regardless and is not the agent's to claim.
    assert result.incremental_recovered_inr == pytest.approx(8_400.0, abs=1.0)


def test_incremental_never_goes_negative() -> None:
    """A run worse than its own counterfactual reports zero, not a refund."""
    cases = [case("bandit", recovered=False) for _ in range(10)]

    assert _aggregate(cases, [], ComplianceSummary()).incremental_recovered_inr == 0.0


def test_cost_per_100_is_zero_rather_than_infinite_when_nothing_recovered() -> None:
    cases = [case("bandit", recovered=False) for _ in range(5)]

    assert _aggregate(cases, [], ComplianceSummary()).cost_per_100_inr_recovered == 0.0


# ── Convergence ────────────────────────────────────────────────────────


def test_a_lucky_window_is_not_convergence() -> None:
    """Labelling the first crossing would be the most flattering misreading available.

    A bandit that leads once by chance and trails for the next ten windows has
    not converged, and a dashed line at that point would tell the reader the
    learning finished three hundred cases before it did.
    """
    series = [
        {"cases": 50, "bandit_rate": 0.40, "baseline_rate": 0.20},
        {"cases": 100, "bandit_rate": 0.10, "baseline_rate": 0.20},
        {"cases": 150, "bandit_rate": 0.30, "baseline_rate": 0.20},
        {"cases": 200, "bandit_rate": 0.35, "baseline_rate": 0.20},
    ]

    assert _convergence_window(series) == 150


def test_never_overtaking_reports_zero_not_the_last_window() -> None:
    series = [{"cases": 50, "bandit_rate": 0.10, "baseline_rate": 0.20}]

    assert _convergence_window(series) == 0


# ── Compliance ─────────────────────────────────────────────────────────


async def test_an_opt_out_stops_contact_whatever_the_arm_said() -> None:
    """It outranks every other rule; there is no hour at which it stops applying."""
    result = await run_batch(None, MERCHANT, n_cases=1000, seed=2, persist_cases=False)

    assert result.opt_outs_honored > 0
    assert result.compliance_summary.opt_outs_honored == result.opt_outs_honored


async def test_violations_are_zero_because_blocks_are_not() -> None:
    """The distinction the field names have to carry.

    A block is the guardrail working. A violation is one that got past it, and
    it is structurally impossible because the check runs before the send. Both
    are reported: the zero alone would hide the work, the blocks alone would
    read as a fault rate.
    """
    result = await run_batch(None, MERCHANT, n_cases=1000, seed=2, persist_cases=False)

    assert result.compliance_violations == 0
    assert result.compliance_summary.rbi_violations == 0
    assert result.compliance_summary.trai_violations == 0
    assert result.compliance_summary.trai_blocks > 0


async def test_a_blocked_case_can_still_recover_on_its_own() -> None:
    """Nothing was sent, so nothing was caused — but the customer may still pay.

    Treating a block as an automatic loss would make the guardrail look far more
    expensive than it is.
    """
    world = module._draw_world(__import__("random").Random(1), "failed_payment")
    world.opted_out = True
    world.self_heals = True

    played = module._play(world, "whatsapp_payment_link", "bandit", "c")

    assert played.blocked_by == "explicit_opt_out"
    assert played.recovered is True
    assert played.intervention_cost_inr == 0.0


# ── Case rows ──────────────────────────────────────────────────────────


async def test_synthetic_cases_are_flagged_and_batched() -> None:
    db = FakeSupabase()
    db.seed_merchant(MERCHANT)

    await run_batch(db, MERCHANT, n_cases=100, seed=1)

    rows = db.rows("recovery_cases")
    assert len(rows) == 100
    assert all(row["metadata"][SYNTHETIC_FLAG] is True for row in rows)
    # Paise on the row, rupees in the result — the row has to match the schema
    # every other reader assumes.
    assert all(isinstance(row["amount_at_risk_cents"], int) for row in rows)


async def test_a_failed_case_insert_does_not_lose_the_result() -> None:
    """The result lives in `batch_runs`; the case rows are a convenience."""

    class Broken(FakeSupabase):
        def table(self, name: str) -> Any:
            if name == "recovery_cases":
                raise ConnectionError("insert failed")
            return super().table(name)

    result = await run_batch(Broken(), MERCHANT, n_cases=100, seed=1)

    assert result.total_cases == 100


async def test_progress_is_written_periodically_not_per_case() -> None:
    """A thousand updates to move a progress bar is a thousand round trips."""
    db = FakeSupabase()
    db.rows("batch_runs").append({"id": "run-1", "merchant_id": MERCHANT, "result": None})
    writes = 0
    original = module._write_progress

    def counting(*args: Any, **kwargs: Any) -> None:
        nonlocal writes
        writes += 1
        original(*args, **kwargs)

    module._write_progress = counting
    try:
        await run_batch(db, MERCHANT, n_cases=1000, seed=1, batch_id="run-1", persist_cases=False)
    finally:
        module._write_progress = original

    assert writes == 1000 // module.PROGRESS_EVERY
    assert db.rows("batch_runs")[0]["result"]["progress"]["cases_done"] == 1000


async def test_the_runner_yields_the_event_loop() -> None:
    """A batch that never awaits would stall every other request for its duration."""
    ticks = 0

    async def counter() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)

    watcher = asyncio.create_task(counter())
    await run_batch(None, MERCHANT, n_cases=500, seed=1, persist_cases=False)
    watcher.cancel()

    assert ticks >= 500 // module.CHUNK


async def test_a_fixed_seed_reproduces_the_whole_run() -> None:
    """Two random streams have to be pinned, not one.

    The world draws use a local generator, but Thompson sampling calls
    `random.betavariate` on the module-level one. Seeding only the local stream
    leaves every arm choice uncontrolled and produces a run that is labelled
    reproducible and is not — which is exactly what a rehearsed demo would
    discover on stage.
    """
    first = await run_batch(None, MERCHANT, n_cases=400, seed=9, persist_cases=False)
    second = await run_batch(None, MERCHANT, n_cases=400, seed=9, persist_cases=False)

    assert first.time_series == second.time_series
    assert first.gross_recovered_inr == second.gross_recovered_inr
    assert first.bandit_convergence_case == second.bandit_convergence_case


async def test_a_seeded_run_does_not_re_seed_the_rest_of_the_process() -> None:
    """A library function that quietly pins the global generator would make
    every later `random` call in the process deterministic too."""
    import random

    random.seed(1234)
    expected = [random.random() for _ in range(3)]

    random.seed(1234)
    await run_batch(None, MERCHANT, n_cases=100, seed=7, persist_cases=False)

    assert [random.random() for _ in range(3)] == expected


# ── The compliance summary ─────────────────────────────────────────────


async def test_the_summary_separates_what_was_blocked_from_what_escaped() -> None:
    """Two numbers that a single "violations" field would collapse.

    Blocks are the guardrail working and are expected to be non-zero.
    Violations are sends that got past it, which cannot happen because the check
    runs first. Reporting one field would either hide the enforcement or
    misreport it as a fault rate.
    """
    result = await run_batch(None, MERCHANT, n_cases=1000, seed=4, persist_cases=False)
    summary = result.compliance_summary

    assert summary.rbi_violations == 0
    assert summary.trai_violations == 0
    assert summary.trai_blocks > 0
    assert summary.opt_outs_honored > 0


async def test_quiet_hours_only_block_messages_not_retries() -> None:
    """TRAI governs contacting a person. A silent retry is not contact, and
    blocking it at 11pm would forgo recoveries the rule never prohibited."""
    import random

    rng = random.Random(3)
    world = module._draw_world(rng, "failed_payment")
    world.opted_out = False
    world.retries_exhausted = False
    world.context["hour_ist"] = 23

    assert module._guardrail_block(world, "whatsapp_payment_link") == "trai_quiet_hours"
    assert module._guardrail_block(world, "silent_retry_next_morning") is None


async def test_the_rbi_ceiling_only_applies_where_the_playbook_has_one() -> None:
    """`checkout_abandonment` has no mandate to retry against, so a retry arm
    there must not be blocked by a rule that does not govern it."""
    import random

    rng = random.Random(3)
    for playbook, expected in (
        ("subscription_failure", "rbi_mandate_retry_count"),
        ("checkout_abandonment", None),
    ):
        world = module._draw_world(rng, playbook)
        world.opted_out = False
        world.retries_exhausted = True
        world.context["hour_ist"] = 10
        assert module._guardrail_block(world, "retry_now") == expected


async def test_human_handoffs_are_counted_because_they_are_what_cost_money() -> None:
    """The expensive arm. It is the reason cost-per-₹100 is on the screen."""
    result = await run_batch(None, MERCHANT, n_cases=1000, seed=4, persist_cases=False)

    assert result.human_handoffs > 0
    assert result.compliance_summary.human_handoffs == result.human_handoffs


# ── The case rows can actually be inserted ─────────────────────────────


async def test_a_synthetic_case_names_the_customer_it_belongs_to() -> None:
    """`recovery_cases.customer_id` is NOT NULL and references `customers`.

    Omitting it fails every insert with 23502 — and because `_insert_cases` is
    deliberately non-fatal, the run still completes and reports a result while
    writing nothing. That is what shipped, and what the fake missed: it did not
    enforce NOT NULL, so a hundred rows landed in the test and zero in Postgres.
    """
    db = FakeSupabase()
    db.seed_merchant(MERCHANT)

    await run_batch(db, MERCHANT, n_cases=100, seed=1)

    rows = db.rows("recovery_cases")
    assert len(rows) == 100
    assert all(row["customer_id"] for row in rows)


async def test_the_customer_pool_is_reused_across_runs() -> None:
    """A thousand new customers per run would dwarf the real ones in every list
    that reads the table."""
    db = FakeSupabase()
    db.seed_merchant(MERCHANT)

    await run_batch(db, MERCHANT, n_cases=100, seed=1)
    first = len(db.rows("customers"))
    await run_batch(db, MERCHANT, n_cases=100, seed=2)

    assert len(db.rows("customers")) == first == module.BATCH_CUSTOMER_POOL


async def test_pool_customers_are_flagged_synthetic() -> None:
    """They are manufactured, and every read that reports money filters on it."""
    db = FakeSupabase()
    db.seed_merchant(MERCHANT)

    await run_batch(db, MERCHANT, n_cases=100, seed=1)

    assert all(row["metadata"][SYNTHETIC_FLAG] for row in db.rows("customers"))


async def test_a_pool_that_cannot_be_built_skips_the_writes_rather_than_failing_each() -> None:
    """No pool means no row can satisfy the foreign key. A thousand rejected
    inserts and a log line each is worse than not trying — the result lives in
    `batch_runs` either way."""

    class NoCustomers(FakeSupabase):
        def table(self, name: str) -> Any:
            if name == "customers":
                raise ConnectionError("customers unavailable")
            return super().table(name)

    db = NoCustomers()
    result = await run_batch(db, MERCHANT, n_cases=100, seed=1)

    assert result.total_cases == 100
    assert db.rows("recovery_cases") == []
