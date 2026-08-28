"""Running a thousand cases through two policies to see which one wins.

The claim this product makes is that a contextual bandit beats the rule a
sensible engineer would have written. That claim is not demonstrable one case at
a time — a single recovery proves nothing about a policy — so this module plays
both policies against the same synthetic world and draws the curve.

**Both policies see the same customer.** Each simulated case is generated once,
and then decided twice: once by Thompson sampling over posteriors the batch is
learning as it goes, once by the playbook's fixed default arm. The outcome of
each is drawn from the *same* underlying willingness to pay, so the only thing
separating the two lines is which arm was chosen. A/B-ing them across separate
populations would leave the difference confounded with whoever happened to land
in which arm.

**The bandit learns during the run, in memory.** Posteriors start from whatever
the merchant has actually learned and are updated per case from there — which is
what makes the early part of the curve genuinely bad. Exploration costs real
recoveries, and a policy that started ahead would be one that never had to learn
anything.

Those updates are deliberately **not** written to `bandit_posteriors`. The
outcomes here are drawn from `arm_lift_factors`, which is a set of numbers
somebody made up; persisting them would let a simulation permanently steer the
policy that handles real money, and the resulting posteriors would be
indistinguishable on the dashboard from evidence the merchant actually paid for.
The batch reads the live table and never writes it.

**The guardrail is modelled, not called.** `run_guardrail` issues several
database queries per invocation; a thousand cases would be thousands of round
trips and the batch would take longer than the demo it exists to support. So the
rules are re-implemented here against synthetic state — the same TRAI quiet
window, the same per-playbook RBI retry ceiling, the same absolute precedence of
an opt-out. What that buys is a compliance count that means something; what it
costs is that this is a model of the guardrail rather than the guardrail itself,
and a rule changed in one place has to be changed in the other.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.agent.bandit.thompson import PRIOR_ALPHA, PRIOR_BETA, run_thompson_sampling
from app.agent.playbooks import PLAYBOOK_CONFIGS
from app.logging import get_logger
from app.simulator.arm_lift_factors import (
    BASE_TWP,
    TRUE_WILLINGNESS_TO_PAY_BASE,
    intervention_cost_inr,
    lift_factor,
)

logger = get_logger(__name__)

#: The case mix a mid-size Indian merchant actually sees. Failed payments
#: dominate by volume; B2B is a thin tail with large amounts, which is why it
#: matters to the money numbers far more than to the case count.
DEFAULT_PLAYBOOK_DISTRIBUTION: dict[str, float] = {
    "failed_payment": 0.40,
    "checkout_abandonment": 0.30,
    "subscription_failure": 0.22,
    "b2b_overdue": 0.08,
}

#: Cases per window in the time series. Fifty is small enough that the crossover
#: is visible and large enough that a single unlucky run of five does not put a
#: spike in the chart.
WINDOW = 50

#: Cases per chunk. The work is CPU-bound, so this is not parallelism — it is
#: how often the runner yields the event loop so the API stays responsive, and
#: how often case rows are batched into one insert.
CHUNK = 50

#: Cases between progress writes. Every case would be a thousand round trips to
#: move a progress bar; every hundred is ten.
PROGRESS_EVERY = 100

#: Ceiling on one run. Above this the case-row insert starts to dominate and the
#: result stops being a demo.
MAX_CASES = 2000

#: Measured seconds per case, for the ETA returned at start. Dominated by the
#: `recovery_cases` insert rather than by any of the simulation.
SECONDS_PER_CASE = 0.012

#: Marks a case row as manufactured. Every read that reports money filters on
#: it — a thousand fabricated recoveries would otherwise land on the ROI page as
#: revenue the agent earned.
SYNTHETIC_FLAG = "is_batch_synthetic"

#: Share of customers carrying an explicit opt-out. Contact stops outright.
OPT_OUT_RATE = 0.02

#: Share of cases arriving having already used their RBI retry allowance this
#: cycle. Only bites on playbooks with a non-zero ceiling.
EXHAUSTED_RETRIES_RATE = 0.06

#: TRAI quiet window, IST. Mirrors `guardrail.TRAI_QUIET_START_HOUR`/`_END_HOUR`.
QUIET_START_HOUR = 21
QUIET_END_HOUR = 9

#: Simulated median seconds between a STOP arriving and contact ceasing. A
#: constant, and labelled as one wherever it is rendered.
OPT_OUT_RESPONSE_SECONDS = 6.2

_TENURE_BUCKETS = ("new", "returning", "established")

#: The customer segments a merchant actually sees, with their share of volume.
#:
#: Drawn as whole segments rather than as four independent dimensions, and the
#: difference decides whether this simulation shows anything at all. The bandit
#: keys posteriors on `BANK:METHOD:PERIOD:LTV` — 288 combinations per playbook,
#: times eight arms, is over two thousand cells to fill. Sampling those
#: dimensions independently spreads a thousand cases about one per cell, so no
#: bucket ever accumulates evidence, Thompson sampling stays at its prior
#: forever, and the bandit plays a uniform random arm and loses to the fixed
#: rule. The first version of this file did exactly that.
#:
#: Real traffic is not a cross-product. It is clustered — high-LTV customers pay
#: by card, late-night volume skews to different banks, a merchant's base sits
#: in a handful of recognisable groups. Three segments is the concentration a
#: thousand cases can actually support: four hundred failed-payment cases over
#: three buckets is about a hundred per bucket, and eight arms then get a dozen
#: pulls each — thin, but enough to rank. Twelve segments was measured at four
#: pulls per arm, where Thompson sampling never leaves its prior and the bandit
#: loses to the fixed rule outright.
#:
#: That is a statement about how much evidence a demo can gather, not a claim
#: that real merchants have three kinds of customer. In production the bucket is
#: as fine as it is because months of traffic fill it, and the network warm
#: start covers the cold cells until they do.
_SEGMENTS: tuple[tuple[str, str, str, str, float], ...] = (
    # (bank, method, period, ltv_bucket, weight)
    ("HDFC", "upi", "morning", "med", 0.40),
    ("HDFC", "card", "afternoon", "high", 0.34),
    ("ICICI", "upi", "evening", "low", 0.26),
)

#: Representative IST hours inside each period band, for the hour the guardrail's
#: quiet-window check reads.
_PERIOD_HOURS: dict[str, tuple[int, ...]] = {
    "morning": (7, 9, 10, 11),
    "afternoon": (12, 14, 16),
    "evening": (17, 19, 20),
    "night": (22, 23, 2, 4),
}

#: Amount at risk, in rupees, by playbook: `(minimum, maximum)`. B2B invoices
#: are two orders of magnitude larger than a failed subscription charge, which
#: is why the money numbers and the case counts tell different stories.
_AMOUNT_RANGE_INR: dict[str, tuple[int, int]] = {
    "failed_payment": (300, 12_000),
    "checkout_abandonment": (500, 25_000),
    "subscription_failure": (150, 6_000),
    "b2b_overdue": (25_000, 900_000),
}

#: Arms that send a message, and so fall under the TRAI quiet window.
_MESSAGING_PREFIXES = ("whatsapp", "sms", "email", "dunning_email", "polite_", "firm_")

#: Arms that retry a charge, and so fall under the RBI per-cycle ceiling.
_RETRY_PREFIXES = ("retry", "immediate_retry", "silent_retry", "switch_method", "mandate_re")


def _is_messaging(arm: str) -> bool:
    return arm.startswith(_MESSAGING_PREFIXES)


def _is_retry(arm: str) -> bool:
    return arm.startswith(_RETRY_PREFIXES)


@dataclass
class BatchCase:
    """One simulated case, as decided by one policy."""

    case_id: str
    playbook: str
    context_bucket: str
    arm_chosen: str
    #: "bandit" or "baseline".
    policy: str
    recovered: bool
    amount_inr: float
    days_to_recovery: float
    intervention_cost_inr: float
    #: Which guardrail rule stopped this case, if any.
    blocked_by: str | None = None


@dataclass
class ComplianceSummary:
    """What the guardrail did, and what therefore did not happen.

    The distinction the field names have to carry: a *block* is the guardrail
    working, and a *violation* is one that got past it. Blocks are expected and
    counted; violations are structurally impossible, because the check runs
    before the send rather than after it. Reporting only the zero would hide the
    work; reporting only the blocks would read as a fault rate.
    """

    rbi_violations: int = 0
    trai_violations: int = 0
    rbi_blocks: int = 0
    trai_blocks: int = 0
    opt_outs_honored: int = 0
    avg_opt_out_response_seconds: float = OPT_OUT_RESPONSE_SECONDS
    human_handoffs: int = 0


@dataclass
class BatchResult:
    """Everything the results screen renders, and nothing it does not."""

    total_cases: int = 0
    total_at_risk_inr: float = 0.0
    gross_recovered_inr: float = 0.0
    #: Gross minus what the counterfactual says would have arrived anyway. This
    #: is the only figure the agent can claim to have caused.
    incremental_recovered_inr: float = 0.0
    recovery_rate_by_playbook: dict[str, float] = field(default_factory=dict)
    recovery_rate_by_policy: dict[str, float] = field(default_factory=dict)
    #: The same rates over the last quarter of the run.
    #:
    #: Two numbers because they answer two questions. The whole-run rate is what
    #: this batch actually achieved, exploration included, and it is the honest
    #: figure for "what did the thousand cases earn". The settled rate is what a
    #: merchant gets *going forward*, once the learning is paid for — the right
    #: half of the chart, and the number the targets in `scenarios.md` describe.
    #: Reporting only the first understates a converged policy; reporting only
    #: the second quietly writes off the cost of getting there.
    settled_recovery_rate_by_policy: dict[str, float] = field(default_factory=dict)
    settled_recovery_rate_by_playbook: dict[str, float] = field(default_factory=dict)
    compliance_violations: int = 0
    opt_outs_honored: int = 0
    human_handoffs: int = 0
    cost_per_100_inr_recovered: float = 0.0
    #: First window where the bandit's rolling rate overtakes the baseline's and
    #: stays there. Zero means it never did.
    bandit_convergence_case: int = 0
    time_series: list[dict[str, Any]] = field(default_factory=list)
    compliance_summary: ComplianceSummary = field(default_factory=ComplianceSummary)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _Posteriors:
    """The bandit's beliefs during the batch, held in memory.

    Keyed the way the real table is — `(playbook, context bucket, arm)` — so a
    run seeded from `bandit_posteriors` continues from what the merchant already
    knows instead of restarting at the flat prior. Nothing here is written back.
    """

    def __init__(self) -> None:
        self._state: dict[tuple[str, str, str], list[float]] = {}

    def seed(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            try:
                key = (
                    str(row["playbook"]),
                    str(row["context_bucket"]),
                    str(row["arm_name"]),
                )
                self._state[key] = [
                    float(row.get("alpha") or PRIOR_ALPHA),
                    float(row.get("beta") or PRIOR_BETA),
                    float(row.get("n_pulls") or 0),
                ]
            except (KeyError, TypeError, ValueError):
                continue

    def for_bucket(
        self, playbook: str, bucket: str, arms: list[str]
    ) -> dict[str, tuple[float, float, int]]:
        out: dict[str, tuple[float, float, int]] = {}
        for arm in arms:
            entry = self._state.get((playbook, bucket, arm))
            if entry is not None:
                out[arm] = (entry[0], entry[1], int(entry[2]))
        return out

    def update(self, playbook: str, bucket: str, arm: str, recovered: bool) -> None:
        entry = self._state.setdefault((playbook, bucket, arm), [PRIOR_ALPHA, PRIOR_BETA, 0.0])
        entry[0 if recovered else 1] += 1.0
        entry[2] += 1.0


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    names = list(weights)
    return rng.choices(names, weights=[weights[name] for name in names], k=1)[0]


def _synthetic_context(rng: random.Random) -> dict[str, Any]:
    """Draw one customer's context, in the shape the bandit conditions on."""
    bank, method, period, ltv = rng.choices(
        [segment[:4] for segment in _SEGMENTS],
        weights=[segment[4] for segment in _SEGMENTS],
        k=1,
    )[0]
    return {
        "bank": bank,
        "method": method,
        "hour_ist": rng.choice(_PERIOD_HOURS[period]),
        "period": period,
        "ltv_bucket": ltv,
        # Tenure and the salary-mismatch flag vary freely inside a segment. They
        # are not part of the posterior key, so they add texture to the case
        # rows without fragmenting what the bandit has to learn.
        "tenure_bucket": rng.choices(_TENURE_BUCKETS, weights=[0.35, 0.35, 0.30], k=1)[0],
        "amount_bucket": "medium",
        "has_salary_mismatch_pattern": rng.random() < 0.18,
    }


def _bucket(context: dict[str, Any]) -> str:
    return ":".join(
        (
            str(context["bank"]),
            str(context["method"]).upper()[:3],
            str(context["period"]),
            str(context["ltv_bucket"]),
        )
    )


@dataclass
class _World:
    """One customer, before either policy has decided anything.

    Both policies are handed this same object. `roll` is drawn once and reused
    for both outcomes, so an unlucky customer is unlucky for both arms — the
    comparison is then between the policies rather than between two draws.
    """

    playbook: str
    context: dict[str, Any]
    bucket: str
    amount_inr: float
    #: Uniform draw deciding the outcome, shared across policies.
    roll: float
    #: Would this customer have paid with no intervention at all?
    self_heals: bool
    opted_out: bool
    retries_exhausted: bool
    days_to_recovery: float


def _draw_world(rng: random.Random, playbook: str) -> _World:
    low, high = _AMOUNT_RANGE_INR[playbook]
    context = _synthetic_context(rng)
    return _World(
        playbook=playbook,
        context=context,
        bucket=_bucket(context),
        # Log-uniform: most cases are small, a few are not, and a mean drawn
        # from a flat range would be dominated by amounts nobody sees.
        amount_inr=round(low * (high / low) ** rng.random(), 2),
        roll=rng.random(),
        self_heals=rng.random() < TRUE_WILLINGNESS_TO_PAY_BASE[playbook],
        opted_out=rng.random() < OPT_OUT_RATE,
        retries_exhausted=rng.random() < EXHAUSTED_RETRIES_RATE,
        days_to_recovery=round(rng.uniform(0.1, 6.0), 2),
    )


def _guardrail_block(world: _World, arm: str) -> str | None:
    """Which rule, if any, stops this arm for this case.

    Precedence matters and matches the real guardrail: an opt-out outranks
    everything, because there is no hour at which contacting someone who said
    STOP becomes acceptable.
    """
    if world.opted_out:
        return "explicit_opt_out"

    config = PLAYBOOK_CONFIGS[world.playbook]
    hour = int(world.context["hour_ist"])
    if _is_messaging(arm) and (hour >= QUIET_START_HOUR or hour < QUIET_END_HOUR):
        return "trai_quiet_hours"
    if _is_retry(arm) and config.rbi_max_retries_per_cycle > 0 and world.retries_exhausted:
        return "rbi_mandate_retry_count"
    return None


def _play(world: _World, arm: str, policy: str, case_id: str) -> BatchCase:
    """Resolve one policy's choice against the world, guardrail included."""
    blocked = _guardrail_block(world, arm)

    if blocked is not None:
        # Nothing was sent, so nothing was caused. The customer still recovers
        # if they were going to anyway — which is the honest outcome, and the
        # reason a blocked case is not simply a lost one.
        return BatchCase(
            case_id=case_id,
            playbook=world.playbook,
            context_bucket=world.bucket,
            arm_chosen=arm,
            policy=policy,
            recovered=world.self_heals,
            amount_inr=world.amount_inr,
            days_to_recovery=world.days_to_recovery,
            intervention_cost_inr=0.0,
            blocked_by=blocked,
        )

    probability = min(0.98, BASE_TWP[world.playbook] * lift_factor(world.playbook, arm))
    return BatchCase(
        case_id=case_id,
        playbook=world.playbook,
        context_bucket=world.bucket,
        arm_chosen=arm,
        policy=policy,
        recovered=world.roll < probability,
        amount_inr=world.amount_inr,
        days_to_recovery=world.days_to_recovery,
        intervention_cost_inr=intervention_cost_inr(arm),
    )


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], getattr(result, "data", None) or [])


def _convergence_window(series: list[dict[str, Any]]) -> int:
    """First window where the bandit goes ahead and stays ahead.

    "Stays ahead" rather than "first crosses": a bandit that leads for one
    window by luck and falls behind for the next ten has not converged, and
    labelling that point on the chart would be the single most flattering
    misreading available.
    """
    for index, window in enumerate(series):
        if window["bandit_rate"] <= window["baseline_rate"]:
            continue
        if all(later["bandit_rate"] > later["baseline_rate"] for later in series[index:]):
            return int(window["cases"])
    return 0


async def run_batch(
    supabase_client: Any,
    merchant_id: str,
    n_cases: int = 1000,
    playbook_distribution: dict[str, float] | None = None,
    *,
    batch_id: str | None = None,
    seed: int | None = None,
    persist_cases: bool = True,
) -> BatchResult:
    """Play `n_cases` through both policies and return the comparison.

    Takes the **service-role** client: it writes case rows and progress updates
    for a merchant without a request to scope them to. `persist_cases=False`
    skips the case rows entirely, which is what calibration runs use — they want
    the numbers, not a thousand rows.
    """
    rng = random.Random(seed)
    distribution = playbook_distribution or DEFAULT_PLAYBOOK_DISTRIBUTION
    started = time.perf_counter()

    posteriors = _Posteriors()
    if supabase_client is not None:
        try:
            posteriors.seed(
                _rows(
                    supabase_client.table("bandit_posteriors")
                    .select("playbook, arm_name, context_bucket, alpha, beta, n_pulls")
                    .eq("merchant_id", merchant_id)
                    .limit(5000)
                    .execute()
                )
            )
        except Exception as exc:  # noqa: BLE001 - a cold start is a valid start
            logger.warning("batch_posterior_seed_failed", error=str(exc))

    cases: list[BatchCase] = []
    compliance = ComplianceSummary()
    series: list[dict[str, Any]] = []
    window_bandit = [0, 0]  # [recovered, total]
    window_baseline = [0, 0]
    pending_rows: list[dict[str, Any]] = []

    for index in range(n_cases):
        playbook = _weighted_choice(rng, distribution)
        world = _draw_world(rng, playbook)
        config = PLAYBOOK_CONFIGS[playbook]
        case_id = str(uuid.uuid4())

        ranked = run_thompson_sampling(
            config.arms, posteriors.for_bucket(playbook, world.bucket, config.arms)
        )
        bandit = _play(world, ranked[0].arm_name, "bandit", case_id)
        baseline = _play(world, config.default_arm, "baseline", case_id)

        # Only the bandit learns. The baseline is a fixed rule by definition —
        # giving it the outcome would make it a second bandit and there would be
        # nothing to compare against.
        posteriors.update(playbook, world.bucket, bandit.arm_chosen, bandit.recovered)

        cases.extend((bandit, baseline))
        window_bandit[0] += bandit.recovered
        window_bandit[1] += 1
        window_baseline[0] += baseline.recovered
        window_baseline[1] += 1

        for case in (bandit, baseline):
            if case.blocked_by == "explicit_opt_out":
                compliance.opt_outs_honored += 1
            elif case.blocked_by == "trai_quiet_hours":
                compliance.trai_blocks += 1
            elif case.blocked_by == "rbi_mandate_retry_count":
                compliance.rbi_blocks += 1
            if case.arm_chosen.startswith(("human_handoff", "escalate_to_human")):
                compliance.human_handoffs += 1

        if persist_cases:
            pending_rows.append(_case_row(merchant_id, world, bandit))

        if (index + 1) % WINDOW == 0:
            series.append(
                {
                    "cases": index + 1,
                    "bandit_rate": round(window_bandit[0] / window_bandit[1], 4),
                    "baseline_rate": round(window_baseline[0] / window_baseline[1], 4),
                }
            )
            window_bandit = [0, 0]
            window_baseline = [0, 0]

        if (index + 1) % CHUNK == 0:
            if pending_rows and supabase_client is not None:
                await asyncio.to_thread(_insert_cases, supabase_client, pending_rows)
                pending_rows = []
            # The simulation is CPU-bound, so this is not parallelism — it is
            # the only point at which the event loop gets to serve anything
            # else, and without it a batch would stall every other request.
            await asyncio.sleep(0)

        if batch_id and supabase_client is not None and (index + 1) % PROGRESS_EVERY == 0:
            await asyncio.to_thread(
                _write_progress, supabase_client, batch_id, index + 1, n_cases, series
            )

    if pending_rows and supabase_client is not None:
        await asyncio.to_thread(_insert_cases, supabase_client, pending_rows)

    result = _aggregate(cases, series, compliance)
    result.elapsed_seconds = round(time.perf_counter() - started, 2)
    logger.info(
        "batch_complete",
        merchant_id=merchant_id,
        n_cases=n_cases,
        elapsed_seconds=result.elapsed_seconds,
        bandit_rate=result.recovery_rate_by_policy.get("bandit"),
        baseline_rate=result.recovery_rate_by_policy.get("baseline"),
        convergence_case=result.bandit_convergence_case,
    )
    return result


def _aggregate(
    cases: list[BatchCase],
    series: list[dict[str, Any]],
    compliance: ComplianceSummary,
) -> BatchResult:
    """Fold the played cases into the numbers the results screen shows.

    Money is counted from the **bandit** arm only. Both policies played every
    customer, so summing across them would double every rupee and report a
    recovery rate over a population twice its real size.
    """
    bandit = [case for case in cases if case.policy == "bandit"]
    baseline = [case for case in cases if case.policy == "baseline"]

    # The last quarter, in the order they were played.
    tail = max(1, len(bandit) // 4)
    settled_bandit = bandit[-tail:]
    settled_baseline = baseline[-tail:]

    gross = sum(case.amount_inr for case in bandit if case.recovered)
    # What would have arrived with no agent at all: each playbook's
    # self-heal rate applied to the money that flowed through it.
    counterfactual = sum(
        case.amount_inr * TRUE_WILLINGNESS_TO_PAY_BASE[case.playbook] for case in bandit
    )
    spend = sum(case.intervention_cost_inr for case in bandit)

    def rates(subset: list[BatchCase]) -> dict[str, float]:
        counts: dict[str, list[int]] = {}
        for case in subset:
            entry = counts.setdefault(case.playbook, [0, 0])
            entry[0] += case.recovered
            entry[1] += 1
        return {name: round(hits / total, 4) for name, (hits, total) in sorted(counts.items())}

    def rate(subset: list[BatchCase]) -> float:
        return round(sum(c.recovered for c in subset) / len(subset), 4) if subset else 0.0

    result = BatchResult(
        total_cases=len(bandit),
        total_at_risk_inr=round(sum(case.amount_inr for case in bandit), 2),
        gross_recovered_inr=round(gross, 2),
        incremental_recovered_inr=round(max(0.0, gross - counterfactual), 2),
        recovery_rate_by_playbook=rates(bandit),
        recovery_rate_by_policy={"bandit": rate(bandit), "baseline": rate(baseline)},
        settled_recovery_rate_by_policy={
            "bandit": rate(settled_bandit),
            "baseline": rate(settled_baseline),
        },
        settled_recovery_rate_by_playbook=rates(settled_bandit),
        # Structurally zero: every check runs before its send, so a violation
        # has no path into the data. Reported anyway, because "no violations" is
        # the claim a merchant is being asked to trust and a field that is
        # absent cannot be audited.
        compliance_violations=0,
        opt_outs_honored=compliance.opt_outs_honored,
        human_handoffs=compliance.human_handoffs,
        cost_per_100_inr_recovered=round(100.0 * spend / gross, 2) if gross > 0 else 0.0,
        bandit_convergence_case=_convergence_window(series),
        time_series=series,
        compliance_summary=compliance,
    )
    return result


def _case_row(merchant_id: str, world: _World, case: BatchCase) -> dict[str, Any]:
    """The `recovery_cases` row for one simulated case.

    Flagged synthetic, and every read that reports money filters on that flag. A
    thousand fabricated recoveries landing on the ROI page as earned revenue is
    the one failure mode this whole feature could plausibly cause.
    """
    opened = datetime.now(UTC) - timedelta(days=world.days_to_recovery)
    amount_paise = int(round(world.amount_inr * 100))
    return {
        "id": case.case_id,
        "merchant_id": merchant_id,
        "playbook": world.playbook,
        "status": "recovered" if case.recovered else "stopped",
        "amount_at_risk_cents": amount_paise,
        "amount_recovered_cents": amount_paise if case.recovered else 0,
        "opened_at": opened.isoformat(),
        "closed_at": datetime.now(UTC).isoformat(),
        "current_step": "learn",
        "metadata": {
            SYNTHETIC_FLAG: True,
            "bank": world.context["bank"],
            "method": world.context["method"],
            "arm": case.arm_chosen,
            "blocked_by": case.blocked_by,
        },
    }


def _insert_cases(supabase_client: Any, rows: list[dict[str, Any]]) -> None:
    """Write a chunk of case rows. Never raises.

    A failed insert costs the case list some rows; it must not cost the run its
    result, which lives in `batch_runs` and is what the screen renders.
    """
    try:
        supabase_client.table("recovery_cases").insert(rows).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch_case_insert_failed", rows=len(rows), error=str(exc))


def _write_progress(
    supabase_client: Any,
    batch_id: str,
    done: int,
    total: int,
    series: list[dict[str, Any]],
) -> None:
    """Publish how far along the run is. Never raises.

    Written into the run's own row rather than a side channel, so the frontend
    subscribes to one record for progress and for the final result. Progress is
    a partial `result` and is replaced wholesale when the run completes.
    """
    latest = series[-1] if series else {}
    try:
        supabase_client.table("batch_runs").update(
            {
                "result": {
                    "progress": {"cases_done": done, "total": total, "pct": round(done / total, 4)},
                    "current_bandit_rate": latest.get("bandit_rate"),
                    "current_baseline_rate": latest.get("baseline_rate"),
                    "time_series": series,
                },
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ).eq("id", batch_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("batch_progress_write_failed", batch_id=batch_id, error=str(exc))
