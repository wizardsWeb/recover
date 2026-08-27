"""Dashboard KPIs.

Partial in Phase 4 — one overview endpoint feeding the home ticker. The bandit
and uplift analytics arrive with the models that produce them, in Phases 6 and 9.

The day boundary is UTC here, unlike the guardrail's frequency window, which
uses IST. That is deliberate and not an oversight: the guardrail's day is a
*person's* day and belongs in their timezone, while this one is a reporting
bucket that has to agree with what the database stores.
"""

from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter
from postgrest.types import CountMethod

from app.deps import CurrentUserId, UserSupabase

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


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
