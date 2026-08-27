"""Dashboard KPIs and bandit analytics.

The day boundary is UTC here, unlike the guardrail's frequency window, which
uses IST. That is deliberate and not an oversight: the guardrail's day is a
*person's* day and belongs in their timezone, while this one is a reporting
bucket that has to agree with what the database stores.

**The two bandit endpoints join in Python, not in Postgres.** PostgREST can
embed a related table but cannot group by an expression across one, and the
grouping these need — cases by day and by the decision source that chose them —
is two cheap reads and a dict. At demo scale that is the simpler correct thing;
if the case table grows past what a single page can return, this becomes a
Postgres view rather than a bigger loop.
"""

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import APIRouter, Query
from postgrest.types import CountMethod

from app.deps import CurrentUserId, UserSupabase

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

#: Decision sources that count as the bandit having chosen. Everything else —
#: a rule fallback, a human override — is the baseline it is measured against,
#: which is why `decide.py` is careful to label its fallback `rule`.
_BANDIT_SOURCE = "bandit"

#: z for a two-sided 95% interval.
_Z_95 = 1.96


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], result.data or [])


@router.get("/overview")
async def get_overview(
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> dict[str, Any]:
    """Return the KPI summary for the dashboard home ticker."""
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    opened = (
        supabase.table("recovery_cases")
        .select("id", count=CountMethod.exact)
        .eq("merchant_id", user_id)
        .gte("opened_at", today_start)
        .execute()
    )

    in_flight = (
        supabase.table("recovery_cases")
        .select("id", count=CountMethod.exact)
        .eq("merchant_id", user_id)
        .eq("status", "in_flight")
        .execute()
    )

    amounts = _rows(
        supabase.table("recovery_cases")
        .select("amount_at_risk_cents, amount_recovered_cents, status")
        .eq("merchant_id", user_id)
        .gte("opened_at", today_start)
        .execute()
    )

    at_risk = sum(row["amount_at_risk_cents"] for row in amounts)
    recovered = sum(row["amount_recovered_cents"] for row in amounts)
    total = len(amounts)
    recovered_count = sum(1 for row in amounts if row["status"] == "recovered")

    return {
        "cases_opened_today": opened.count or 0,
        "cases_in_flight": in_flight.count or 0,
        "amount_at_risk_today_cents": at_risk,
        "amount_recovered_today_cents": recovered,
        "recovery_rate_today": round(recovered_count / total, 3) if total > 0 else 0.0,
        # Always zero by construction: the guardrail blocks before an action is
        # taken, so a violation cannot reach the database. It is reported anyway
        # because "zero violations" is the claim the merchant is being asked to
        # trust, and a field that is absent cannot be audited.
        "compliance_violations_today": 0,
    }


@router.get("/bandit-curve")
async def get_bandit_curve(
    user_id: CurrentUserId,
    supabase: UserSupabase,
    playbook: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
) -> dict[str, Any]:
    """Recovery rate per day, split by who chose the action.

    The comparison is the claim the product makes — that a bandit beats a fixed
    rule — so the two series are computed the same way over the same cases and
    differ only in which decision source produced them. A day with no cases in a
    series is absent rather than zero: a zero recovery rate and no attempts are
    very different facts and a chart should not conflate them.
    """
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    case_query = (
        supabase.table("recovery_cases")
        .select("id, status, opened_at, playbook")
        .eq("merchant_id", user_id)
        .gte("opened_at", since)
    )
    if playbook:
        case_query = case_query.eq("playbook", playbook)
    cases = _rows(case_query.execute())

    if not cases:
        return {
            "series": {"bandit": [], "baseline": []},
            "summary": {
                "bandit_avg_rate": 0.0,
                "baseline_avg_rate": 0.0,
                "lift_pct": 0.0,
                "total_cases": 0,
            },
        }

    # One read for every decide row, then matched in memory. Filtering by the
    # case ids we already have keeps this scoped to the window rather than
    # pulling the merchant's whole decision history.
    decisions = _rows(
        supabase.table("agent_decisions")
        .select("case_id, decision_source")
        .eq("merchant_id", user_id)
        .eq("step_name", "decide")
        .in_("case_id", [str(row["id"]) for row in cases])
        .execute()
    )
    source_by_case = {
        str(row["case_id"]): str(row.get("decision_source") or "") for row in decisions
    }

    # (series, date) -> [recovered, total]
    tally: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for case in cases:
        source = source_by_case.get(str(case["id"]))
        if source is None:
            # A case that never reached DECIDE — blocked at the uplift check, or
            # still mid-pass. It belongs to neither series.
            continue
        series = "bandit" if source == _BANDIT_SOURCE else "baseline"
        day = str(case["opened_at"])[:10]
        bucket = tally[(series, day)]
        bucket[0] += 1 if case["status"] == "recovered" else 0
        bucket[1] += 1

    def points(series: str) -> list[dict[str, Any]]:
        return [
            {
                "date": day,
                "recovery_rate": round(recovered / total, 4) if total else 0.0,
                "n_cases": total,
            }
            for (name, day), (recovered, total) in sorted(tally.items())
            if name == series
        ]

    def average(series: str) -> tuple[float, int]:
        recovered = sum(v[0] for k, v in tally.items() if k[0] == series)
        total = sum(v[1] for k, v in tally.items() if k[0] == series)
        return (recovered / total if total else 0.0), total

    bandit_rate, bandit_n = average("bandit")
    baseline_rate, baseline_n = average("baseline")

    return {
        "series": {"bandit": points("bandit"), "baseline": points("baseline")},
        "summary": {
            "bandit_avg_rate": round(bandit_rate, 4),
            "baseline_avg_rate": round(baseline_rate, 4),
            # Relative lift, and undefined rather than infinite when the
            # baseline never recovered anything — a divide-by-zero rendered as a
            # huge percentage is the kind of number that ends up on a slide.
            "lift_pct": (
                round((bandit_rate - baseline_rate) / baseline_rate * 100, 2)
                if baseline_rate > 0
                else None
            ),
            "total_cases": bandit_n + baseline_n,
        },
    }


@router.get("/bandit-posteriors")
async def get_bandit_posteriors(
    user_id: CurrentUserId,
    supabase: UserSupabase,
    playbook: str = Query(...),
    context_bucket: str | None = Query(default=None),
) -> dict[str, Any]:
    """Current Beta posteriors per arm, with an interval around each mean.

    The interval is what stops the table being read as a leaderboard. An arm at
    100% over two pulls and an arm at 71% over forty are not comparable, and the
    width of the interval is the only thing on the row that says so.
    """
    query = (
        supabase.table("bandit_posteriors")
        .select("arm_name, alpha, beta, n_pulls, context_bucket, last_updated_at")
        .eq("merchant_id", user_id)
        .eq("playbook", playbook)
    )
    if context_bucket:
        query = query.eq("context_bucket", context_bucket)

    arms = [
        _posterior_row(row)
        for row in sorted(
            _rows(query.execute()),
            key=lambda r: (
                float(r.get("alpha") or 1)
                / max(float(r.get("alpha") or 1) + float(r.get("beta") or 1), 1e-9)
            ),
            reverse=True,
        )
    ]

    return {"playbook": playbook, "context_bucket": context_bucket, "arms": arms}


def _posterior_row(row: dict[str, Any]) -> dict[str, Any]:
    """One arm's posterior with its mean and 95% interval."""
    alpha = float(row.get("alpha") or 1.0)
    beta = float(row.get("beta") or 1.0)
    mass = alpha + beta
    mean = alpha / mass if mass > 0 else 0.5
    ci_low, ci_high = _confidence_interval(mean, mass)

    return {
        "arm_name": row.get("arm_name"),
        "context_bucket": row.get("context_bucket"),
        "alpha": alpha,
        "beta": beta,
        "n_pulls": int(row.get("n_pulls") or 0),
        "expected_win_rate": round(mean, 4),
        "ci_low": round(ci_low, 4),
        "ci_high": round(ci_high, 4),
        "last_updated_at": row.get("last_updated_at"),
    }


def _confidence_interval(mean: float, mass: float) -> tuple[float, float]:
    """A normal approximation to the 95% interval on a Beta posterior.

    ``n`` subtracts the Beta(1,1) prior's two pseudo-observations, so an arm
    that has never been pulled reports the full ``[0, 1]`` — which is the honest
    interval for "no evidence" and renders as a bar spanning the whole row
    rather than a confident-looking point at 50%.
    """
    n = mass - 2.0
    if n <= 0:
        return 0.0, 1.0
    margin = _Z_95 * math.sqrt(max(mean * (1.0 - mean), 0.0) / n)
    return max(0.0, mean - margin), min(1.0, mean + margin)
