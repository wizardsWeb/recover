"""Manufacturing an uplift history the model can actually learn from.

The T-learner needs two groups with observed outcomes, and the honest way to get
them is to run the agent for a few months with 5% of cases held out. A demo does
not have a few months. This module fabricates the history instead.

**What is fabricated is the ground truth, not the machinery.** Every row goes
through the same tables the live loop writes — ``recovery_cases``,
``agent_decisions.bandit_context_vector`` for the treated, ``uplift_holdouts``
for the controls — and training afterwards reads them with the same queries it
uses in production. Nothing here writes a snapshot directly; the model still has
to find the effect.

So the interesting part is the generative process. Each case is drawn from one of
four latent segments with genuinely different treatment effects: contacting a
*persuadable* customer roughly doubles their recovery rate, a *sure thing*
recovers with or without the message, a *lost cause* recovers in neither arm, and
a *do-not-disturb* customer recovers **less** when contacted. Each segment then
draws context features from its own distribution, which is what makes the effect
recoverable — a model fitted on features that carry no segment information would
correctly report a flat effect, and the demo would show four identical buckets.

Bank is drawn independently of segment on purpose. It is the noise dimension:
something for the model to correctly find nothing in, and the feature most likely
to contain a value the snapshot has never seen.

**Two deliberate departures from the live policy.**

* *The holdout share is far above 5%.* At 5%, reaching the ten resolved controls
  ``MIN_GROUP_SAMPLES`` demands would take about 800 cases in the smallest
  playbook alone. The seeder is producing a training corpus, not simulating the
  assignment policy, so it holds out about a quarter and floors each playbook at
  ``MIN_CONTROLS_PER_PLAYBOOK``. Without that floor ``b2b_overdue`` — a tenth of
  the volume — trains on nothing and the ROI page shows three buckets and a
  shrug.
* *``uplift_bucket`` on a seeded case is the generating segment, not a
  prediction.* These cases closed before any model existed. Recording what they
  were actually drawn from is the only truthful value available, and it is more
  useful than null: the case list has something to render, and it is the label a
  prediction can be checked against.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from app.logging import get_logger
from app.ml.uplift.model import MIN_GROUP_SAMPLES

logger = get_logger(__name__)

#: Share of seeded volume per playbook. Uneven on purpose — a merchant's case mix
#: is never uniform, and a flat split would hide the small-playbook problem the
#: control floor below exists to solve.
PLAYBOOK_WEIGHTS: dict[str, float] = {
    "subscription_failure": 0.40,
    "checkout_abandonment": 0.30,
    "failed_payment": 0.20,
    "b2b_overdue": 0.10,
}

#: Controls per playbook, whatever its share of the volume. Five above the
#: training minimum so that a run is not one unlucky draw away from
#: `insufficient_data`.
MIN_CONTROLS_PER_PLAYBOOK = MIN_GROUP_SAMPLES + 5

#: Roughly a quarter held out. See the module docstring: this is a corpus, not
#: the production assignment rate.
DEFAULT_HOLDOUT_RATE = 0.25

#: Enough cases that every playbook has a treated group worth fitting, and few
#: enough that the whole seed is a couple of round trips.
DEFAULT_TOTAL_CASES = 320

#: Cap on what one call may manufacture. The endpoint is dev-gated, but a typo'd
#: zero should cost a rejection rather than a hundred thousand rows.
MAX_TOTAL_CASES = 2000

#: Rows per insert. PostgREST takes the whole batch in one statement and returns
#: the inserted rows in order, which is what lets a case be zipped back to the
#: decision or holdout row that belongs to it.
_CHUNK = 100

#: Drawn independently of segment: the dimension the model should find nothing
#: in. `NEWB` is never seeded, so a later prediction carrying it exercises the
#: unseen-category path.
_BANKS = ("HDFC", "ICIC", "SBI", "AXIS", "KOTA", "YESB")

_HOURS: dict[str, tuple[int, ...]] = {
    "morning": (7, 9, 10, 11),
    "afternoon": (12, 14, 16),
    "evening": (17, 19, 20),
    "night": (22, 23, 2, 4),
}

#: Amount bands in paise, matching `_amount_bucket`'s boundaries from below and
#: above rather than sitting on them.
_AMOUNTS: dict[str, tuple[int, int]] = {
    "small": (20_000, 99_000),
    "medium": (120_000, 900_000),
    "large": (1_100_000, 8_000_000),
}

#: LTV and tenure values that land in each bucket, for the customer rows the
#: cases point at. The context vector is derived from the customer in the live
#: loop, so seeding a customer whose LTV contradicts the case's stated bucket
#: would leave the two disagreeing the moment anything recomputed.
_LTV_CENTS: dict[str, int] = {"low": 120_000, "med": 900_000, "high": 4_000_000}
_TENURE_DAYS: dict[str, int] = {"new": 12, "returning": 90, "established": 400}


@dataclass(frozen=True)
class Segment:
    """A latent customer type with its own response to being contacted.

    ``treated_rate`` and ``control_rate`` are the two potential outcomes; their
    difference is the true CATE the T-learner is being asked to recover.
    """

    bucket: str
    weight: float
    treated_rate: float
    control_rate: float
    periods: tuple[str, ...]
    ltv_buckets: tuple[str, ...]
    tenure_buckets: tuple[str, ...]
    methods: tuple[str, ...]
    amount_buckets: tuple[str, ...]
    salary_mismatch: bool = False
    past_failures: tuple[int, ...] = field(default=(0, 1))


SEGMENTS: tuple[Segment, ...] = (
    # The segment the whole system is for: a message roughly doubles recovery.
    Segment(
        bucket="persuadable",
        weight=0.42,
        treated_rate=0.76,
        control_rate=0.31,
        periods=("morning", "afternoon"),
        ltv_buckets=("med", "high"),
        tenure_buckets=("returning", "established"),
        methods=("UPI", "CAR"),
        amount_buckets=("medium", "large"),
    ),
    # Would have paid anyway. Gross recovery counts these; incremental must not.
    Segment(
        bucket="sure_thing",
        weight=0.24,
        treated_rate=0.91,
        control_rate=0.84,
        periods=("morning", "evening"),
        ltv_buckets=("high",),
        tenure_buckets=("established",),
        methods=("CAR", "NET"),
        amount_buckets=("small",),
    ),
    # Recovers in neither arm. The message is wasted, not harmful.
    Segment(
        bucket="lost_cause",
        weight=0.24,
        treated_rate=0.11,
        control_rate=0.09,
        periods=("afternoon", "evening"),
        ltv_buckets=("low",),
        tenure_buckets=("new",),
        methods=("WAL", "NET"),
        amount_buckets=("small", "medium"),
    ),
    # The segment that justifies the holdout group's cost: contact makes them
    # worse, and without a control arm there is no way to see it.
    Segment(
        bucket="dnd",
        weight=0.10,
        treated_rate=0.27,
        control_rate=0.52,
        periods=("night",),
        ltv_buckets=("low", "med"),
        tenure_buckets=("new",),
        methods=("UPI", "MAN"),
        amount_buckets=("large",),
        salary_mismatch=True,
        past_failures=(2, 3, 4),
    ),
)


@dataclass
class _PlannedCase:
    """One synthetic case, before anything is written."""

    playbook: str
    segment: Segment
    context: dict[str, Any]
    is_holdout: bool
    recovered: bool
    amount_at_risk_cents: int
    ltv_bucket: str
    tenure_bucket: str
    opened_at: datetime
    closed_at: datetime


def _pick_segment(rng: random.Random) -> Segment:
    return rng.choices(SEGMENTS, weights=[s.weight for s in SEGMENTS], k=1)[0]


def _plan_case(playbook: str, *, is_holdout: bool, rng: random.Random) -> _PlannedCase:
    """Draw a segment, then draw everything else from it."""
    segment = _pick_segment(rng)

    period = rng.choice(segment.periods)
    ltv_bucket = rng.choice(segment.ltv_buckets)
    tenure_bucket = rng.choice(segment.tenure_buckets)
    amount_bucket = rng.choice(segment.amount_buckets)
    low, high = _AMOUNTS[amount_bucket]
    past_failures = rng.choice(segment.past_failures)

    context = {
        "bank": rng.choice(_BANKS),
        "method": rng.choice(segment.methods),
        "hour_ist": rng.choice(_HOURS[period]),
        "period": period,
        "ltv_bucket": ltv_bucket,
        "tenure_bucket": tenure_bucket,
        "amount_bucket": amount_bucket,
        "past_failure_count": past_failures,
        "has_salary_mismatch_pattern": segment.salary_mismatch,
    }

    rate = segment.control_rate if is_holdout else segment.treated_rate
    opened_at = datetime.now(UTC) - timedelta(
        days=rng.randint(1, 60), hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
    )

    return _PlannedCase(
        playbook=playbook,
        segment=segment,
        context=context,
        is_holdout=is_holdout,
        recovered=rng.random() < rate,
        amount_at_risk_cents=rng.randint(low, high),
        ltv_bucket=ltv_bucket,
        tenure_bucket=tenure_bucket,
        opened_at=opened_at,
        closed_at=opened_at + timedelta(hours=rng.randint(2, 72)),
    )


def _allocate(total_cases: int, holdout_rate: float) -> dict[str, tuple[int, int]]:
    """Split the volume into ``(treated, control)`` counts per playbook.

    The control floor is applied after the proportional split, so a small
    playbook ends up over-sampled for controls rather than untrainable.
    """
    allocation: dict[str, tuple[int, int]] = {}
    for playbook, weight in PLAYBOOK_WEIGHTS.items():
        share = max(int(round(total_cases * weight)), MIN_CONTROLS_PER_PLAYBOOK * 2)
        controls = max(int(round(share * holdout_rate)), MIN_CONTROLS_PER_PLAYBOOK)
        allocation[playbook] = (share - controls, controls)
    return allocation


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], getattr(result, "data", None) or [])


def _insert_chunked(
    supabase_client: Any, table: str, payload: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    written: list[dict[str, Any]] = []
    for start in range(0, len(payload), _CHUNK):
        chunk = payload[start : start + _CHUNK]
        written.extend(_rows(supabase_client.table(table).insert(chunk).execute()))
    return written


def _ensure_customers(supabase_client: Any, merchant_id: str) -> dict[tuple[str, str], list[str]]:
    """One synthetic customer per LTV × tenure combination, created once.

    Cases point at a customer whose stored LTV and tenure land in the same
    buckets their context vector claims. Anything that recomputes the vector
    later — a re-diagnosis, a backfill — then gets the same answer instead of
    silently contradicting the training data.
    """
    existing = _rows(
        supabase_client.table("customers")
        .select("id, external_id")
        .eq("merchant_id", merchant_id)
        .like("external_id", "uplift-seed-%")
        .execute()
    )
    by_key: dict[tuple[str, str], list[str]] = {}
    for row in existing:
        parts = str(row.get("external_id") or "").split("-")
        if len(parts) >= 5:
            by_key.setdefault((parts[2], parts[3]), []).append(str(row["id"]))

    pending: list[dict[str, Any]] = []
    for ltv_bucket, ltv_cents in _LTV_CENTS.items():
        for tenure_bucket, tenure_days in _TENURE_DAYS.items():
            key = (ltv_bucket, tenure_bucket)
            for index in range(3 - len(by_key.get(key, []))):
                pending.append(
                    {
                        "merchant_id": merchant_id,
                        "external_id": f"uplift-seed-{ltv_bucket}-{tenure_bucket}-{index}",
                        "name": f"Seed {ltv_bucket.title()} / {tenure_bucket.title()} {index + 1}",
                        "phone": f"+9198{abs(hash(key)) % 100:02d}{index}00000"[:13],
                        "email": f"seed-{ltv_bucket}-{tenure_bucket}-{index}@example.invalid",
                        "ltv_cents": ltv_cents,
                        "tenure_days": tenure_days,
                    }
                )

    for row in _insert_chunked(supabase_client, "customers", pending):
        parts = str(row.get("external_id") or "").split("-")
        by_key.setdefault((parts[2], parts[3]), []).append(str(row["id"]))
    return by_key


def seed_uplift_history(
    supabase_client: Any,
    merchant_id: str,
    *,
    total_cases: int = DEFAULT_TOTAL_CASES,
    holdout_rate: float = DEFAULT_HOLDOUT_RATE,
    seed: int | None = None,
) -> dict[str, Any]:
    """Write a synthetic treated/control history and return what was written.

    ``seed`` fixes the draw. A reproducible corpus is worth having: a demo that
    shows a different effect size on every run is one nobody can rehearse, and
    the tests need the same guarantee.
    """
    rng = random.Random(seed)
    customers = _ensure_customers(supabase_client, merchant_id)

    plans: list[_PlannedCase] = []
    for playbook, (treated, controls) in _allocate(total_cases, holdout_rate).items():
        plans.extend(_plan_case(playbook, is_holdout=False, rng=rng) for _ in range(treated))
        plans.extend(_plan_case(playbook, is_holdout=True, rng=rng) for _ in range(controls))
    rng.shuffle(plans)

    case_rows: list[dict[str, Any]] = []
    for plan in plans:
        pool = customers[(plan.ltv_bucket, plan.tenure_bucket)]
        case_rows.append(
            {
                "merchant_id": merchant_id,
                "customer_id": rng.choice(pool),
                "playbook": plan.playbook,
                "status": _status_for(plan),
                "amount_at_risk_cents": plan.amount_at_risk_cents,
                "amount_recovered_cents": plan.amount_at_risk_cents if plan.recovered else 0,
                "opened_at": plan.opened_at.isoformat(),
                "closed_at": plan.closed_at.isoformat(),
                "current_step": "learn",
                "uplift_bucket": plan.segment.bucket,
                "is_holdout": plan.is_holdout,
                "metadata": {
                    "seeded": True,
                    "bank": plan.context["bank"],
                    "method": plan.context["method"],
                },
            }
        )

    written = _insert_chunked(supabase_client, "recovery_cases", case_rows)
    if len(written) != len(plans):
        # Zipping a short insert back onto the plan would attach one case's
        # context to another's outcome, which trains a model on scrambled
        # labels and reports it as success.
        raise RuntimeError(
            f"Seeded {len(plans)} cases but the database returned {len(written)} rows."
        )

    decisions: list[dict[str, Any]] = []
    holdouts: list[dict[str, Any]] = []
    for plan, row in zip(plans, written, strict=True):
        if plan.is_holdout:
            holdouts.append(
                {
                    "case_id": row["id"],
                    "merchant_id": merchant_id,
                    "assigned_at": plan.opened_at.isoformat(),
                    "holdout_reason": "seeded_control",
                    "outcome": "recovered" if plan.recovered else "not_recovered",
                    "outcome_amount_cents": plan.amount_at_risk_cents if plan.recovered else 0,
                    "context_features": plan.context,
                }
            )
        else:
            decisions.append(
                {
                    "case_id": row["id"],
                    "merchant_id": merchant_id,
                    "step_number": 4,
                    "step_name": "decide",
                    "decision_source": "bandit",
                    "bandit_context_vector": plan.context,
                    "reasoning": "Seeded history — the arm this case was worked under.",
                }
            )

    _insert_chunked(supabase_client, "agent_decisions", decisions)
    _insert_chunked(supabase_client, "uplift_holdouts", holdouts)

    logger.info(
        "uplift_history_seeded",
        merchant_id=merchant_id,
        cases=len(written),
        treated=len(decisions),
        controls=len(holdouts),
    )
    return {
        "cases": len(written),
        "treated": len(decisions),
        "controls": len(holdouts),
        "customers": sum(len(ids) for ids in customers.values()),
    }


def _status_for(plan: _PlannedCase) -> str:
    """The case status a real run would have left behind.

    A control that recovered still reads as ``holdout``: the point of the status
    is which arm the case was in, and losing that would make the control group
    unidentifiable from the case table alone.
    """
    if plan.is_holdout:
        return "holdout"
    return "recovered" if plan.recovered else "stopped"
