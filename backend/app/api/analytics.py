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


#: Statuses that mean a case has an observed outcome. An open case has nothing
#: to attribute yet, and counting it would dilute every rate on the page.
_CLOSED_STATUSES = frozenset({"recovered", "stopped", "failed", "holdout"})

#: Holdout outcomes that count as observed. `unknown` is an assigned control
#: nobody has resolved: it teaches nothing and must not enter the denominator,
#: where it would read as a failure to recover and inflate measured lift.
_RESOLVED_OUTCOMES = frozenset({"recovered", "not_recovered"})

#: Bucket for a case that closed before any model could label it. Real holdouts
#: are assigned at detect, before diagnosis, so this is the normal state for a
#: control — not an error.
_UNBUCKETED = "unknown"

_NO_CONTROLS_NOTE = (
    "No resolved holdout cases yet, so incremental recovery cannot be estimated. "
    "Gross recovery is every rupee that arrived after the agent acted — including "
    "from customers who would have paid anyway. Until a control group resolves, "
    "there is no way to tell those apart, and this page will not guess."
)

_METHODOLOGY_NOTE = (
    "Gross recovery counts every rupee recovered on a case the agent worked. "
    "Incremental recovery is what the agent caused: within each uplift bucket, the "
    "treated recovery rate minus the rate observed in the holdout group, applied to "
    "that bucket's gross. Customers who would have paid regardless contribute close "
    "to nothing, and a bucket where contact hurt contributes a negative amount. "
    "The holdout group is the only reason the two numbers can differ — without cases "
    "the agent deliberately left alone, there is nothing to compare against."
)


def _recovered(case: dict[str, Any]) -> bool:
    return int(case.get("amount_recovered_cents") or 0) > 0


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


@router.get("/uplift")
async def get_uplift_roi(
    user_id: CurrentUserId,
    supabase: UserSupabase,
    playbook: str | None = Query(default=None),
) -> dict[str, Any]:
    """Gross recovery against the part of it the agent actually caused.

    The two numbers answer different questions and the gap between them is the
    point of the page. Gross is what a recovery dashboard normally reports:
    money that arrived after a message. Incremental subtracts what would have
    arrived anyway, which is knowable only because a slice of cases was
    deliberately left alone.

    Attribution happens here rather than in the agent loop. The loop still
    messages a `sure_thing` — the send is nearly free and the recovery is real —
    but a recovery from a customer who was going to pay regardless is not
    *caused*, and the difference-in-rates below is where that is charged back.

    With no resolved controls the response reports gross and says plainly that
    incremental is unknown. A plausible-looking number derived from no control
    group would be the single most misleading thing this product could render.
    """
    query = (
        supabase.table("recovery_cases")
        .select(
            "id, playbook, status, uplift_bucket, is_holdout, "
            "amount_at_risk_cents, amount_recovered_cents"
        )
        .eq("merchant_id", user_id)
    )
    if playbook:
        query = query.eq("playbook", playbook)
    cases = [row for row in _rows(query.execute()) if row.get("status") in _CLOSED_STATUSES]

    resolved_controls = {
        str(row["case_id"])
        for row in _rows(
            supabase.table("uplift_holdouts")
            .select("case_id, outcome")
            .eq("merchant_id", user_id)
            .execute()
        )
        if row.get("outcome") in _RESOLVED_OUTCOMES
    }

    treated = [case for case in cases if not case.get("is_holdout")]
    control = [
        case
        for case in cases
        if case.get("is_holdout") and str(case.get("id")) in resolved_controls
    ]

    gross_cents = sum(int(case.get("amount_recovered_cents") or 0) for case in treated)
    control_recovered = sum(1 for case in control if _recovered(case))
    global_control_rate = _rate(control_recovered, len(control))

    holdout_stats = {
        "holdout_cases": sum(1 for case in cases if case.get("is_holdout")),
        "resolved_controls": len(control),
        "control_recoveries": control_recovered,
        "control_recovery_rate": global_control_rate,
        "treated_cases": len(treated),
        "treated_recovery_rate": _rate(
            sum(1 for case in treated if _recovered(case)), len(treated)
        ),
        "holdout_share": _rate(len(control), len(control) + len(treated)),
    }

    if not control:
        return {
            "gross_recovery_cents": gross_cents,
            "incremental_recovery_cents": None,
            "incremental_pct_of_gross": None,
            "is_estimable": False,
            "bucket_breakdown": [],
            "holdout_stats": holdout_stats,
            "methodology_note": _NO_CONTROLS_NOTE,
        }

    breakdown = _bucket_breakdown(treated, control, global_control_rate)
    incremental_cents = sum(int(row["incremental_recovery_cents"]) for row in breakdown)

    # What the control group cost: the recoveries those cases would have
    # produced had they been worked. Stating it is the only way the 5% is an
    # informed choice rather than an invisible tax.
    treated_rate = float(holdout_stats["treated_recovery_rate"])
    avg_control_at_risk = sum(int(case.get("amount_at_risk_cents") or 0) for case in control) / len(
        control
    )
    holdout_stats["foregone_recovery_cents"] = max(
        0, round((treated_rate - global_control_rate) * len(control) * avg_control_at_risk)
    )

    return {
        "gross_recovery_cents": gross_cents,
        "incremental_recovery_cents": incremental_cents,
        "incremental_pct_of_gross": _rate(incremental_cents, gross_cents) if gross_cents else None,
        "is_estimable": True,
        "bucket_breakdown": breakdown,
        "holdout_stats": holdout_stats,
        "methodology_note": _METHODOLOGY_NOTE,
    }


def _bucket_breakdown(
    treated: list[dict[str, Any]],
    control: list[dict[str, Any]],
    global_control_rate: float,
) -> list[dict[str, Any]]:
    """Per-bucket lift, and the share of gross it accounts for.

    A bucket's own control rate is used when it has controls of its own.
    Otherwise the global rate stands in — a real holdout is assigned before
    diagnosis and so usually carries no bucket at all, which would otherwise
    leave every bucket with an empty comparison and a lift of exactly its own
    recovery rate.
    """
    treated_by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in treated:
        treated_by_bucket[str(case.get("uplift_bucket") or _UNBUCKETED)].append(case)

    control_by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in control:
        control_by_bucket[str(case.get("uplift_bucket") or _UNBUCKETED)].append(case)

    rows: list[dict[str, Any]] = []
    for bucket, cases in sorted(treated_by_bucket.items()):
        controls = control_by_bucket.get(bucket, [])
        uses_global = len(controls) < 2
        control_rate = (
            global_control_rate
            if uses_global
            else _rate(sum(1 for case in controls if _recovered(case)), len(controls))
        )

        recovered_count = sum(1 for case in cases if _recovered(case))
        treated_rate = _rate(recovered_count, len(cases))
        bucket_gross = sum(int(case.get("amount_recovered_cents") or 0) for case in cases)
        lift = round(treated_rate - control_rate, 4)

        # gross == treated_rate x cases x average recovery, so scaling gross by
        # lift/treated_rate is the same as pricing the lift at that average —
        # without a second division that would need its own zero guard.
        incremental = round(bucket_gross * lift / treated_rate) if treated_rate > 0 else 0

        rows.append(
            {
                "bucket": bucket,
                "treated_cases": len(cases),
                "treated_recovery_rate": treated_rate,
                "control_cases": len(controls),
                "control_recovery_rate": control_rate,
                "uses_global_control_rate": uses_global,
                "estimated_lift": lift,
                "gross_recovery_cents": bucket_gross,
                "incremental_recovery_cents": incremental,
            }
        )
    return rows
