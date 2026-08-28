"""Playbook configuration and per-playbook statistics.

A playbook is the agent's operating envelope for one kind of leak: which arms it
may play, how often it may speak, and when it must stop. The envelope itself
lives in code (``app.agent.playbooks``) because it is a compliance artefact —
one file per playbook that a reviewer can read end to end — and the only part a
merchant can change from the UI is whether the playbook runs at all.

That switch lives in ``merchants.playbook_config``, keyed by playbook slug. A
playbook with no entry is **on**: the four playbooks are the product, and a
merchant who has never opened this page should have all four working rather than
none. Absence therefore means default-enabled, not disabled.

Stats are computed per request from ``recovery_cases`` rather than kept in a
counter. At demo scale that is a single scan, and a counter would be a second
source of truth for numbers the case table already answers exactly.
"""

from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.agent.playbooks import PLAYBOOK_CONFIGS, get_playbook_config
from app.deps import CurrentUserId, UserSupabase
from app.logging import get_logger

router = APIRouter(prefix="/api/playbooks", tags=["playbooks"])
log = get_logger(__name__)

#: Merchant-facing names. The slugs are database values and are not shown.
PLAYBOOK_LABELS: dict[str, str] = {
    "failed_payment": "Failed payments",
    "checkout_abandonment": "Abandoned checkouts",
    "subscription_failure": "Subscription failures",
    "b2b_overdue": "Overdue invoices",
}

PLAYBOOK_DESCRIPTIONS: dict[str, str] = {
    "failed_payment": "A one-off payment that did not go through — retry, or nudge, or wait.",
    "checkout_abandonment": "A full cart that never became an order.",
    "subscription_failure": "A recurring charge the mandate could not collect.",
    "b2b_overdue": "An invoice past its terms, worked up a ladder of escalating tone.",
}

#: Statuses that count as the agent still holding the case.
_ACTIVE = ("open", "in_flight")


class CamelModel(BaseModel):
    """Base model that speaks camelCase on the wire and snake_case in Python."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)


class PlaybookStats(CamelModel):
    total_cases: int = 0
    cases_open: int = 0
    cases_in_flight: int = 0
    cases_recovered: int = 0
    recovery_rate: float = 0.0
    amount_at_risk_cents: int = 0
    amount_recovered_cents: int = 0
    #: Mean hours from opened to closed, over recovered cases only. ``None``
    #: when nothing has been recovered yet — a zero would read as "instant".
    avg_hours_to_recovery: float | None = None


class PlaybookSummary(CamelModel):
    slug: str
    label: str
    description: str
    enabled: bool
    default_arm: str
    arm_count: int
    stats: PlaybookStats


class ToggleResponse(CamelModel):
    slug: str
    enabled: bool


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], result.data or [])


def _require_known(slug: str) -> None:
    if slug not in PLAYBOOK_CONFIGS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown playbook: {slug}"
        )


def _merchant_row(supabase: Any, user_id: str) -> dict[str, Any]:
    resp = supabase.table("merchants").select("*").eq("id", user_id).limit(1).execute()
    if not resp.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Merchant not found")
    return _rows(resp)[0]


def is_enabled(playbook_config: dict[str, Any], slug: str) -> bool:
    """Whether this playbook runs. Absent means on — see the module docstring."""
    entry = playbook_config.get(slug)
    if isinstance(entry, dict):
        return bool(entry.get("enabled", True))
    if isinstance(entry, bool):
        return entry
    return True


def _stats_for(cases: list[dict[str, Any]]) -> PlaybookStats:
    """Fold a playbook's cases into the numbers the UI shows."""
    if not cases:
        return PlaybookStats()

    recovered = [c for c in cases if c["status"] == "recovered"]
    durations = [
        hours
        for c in recovered
        if (hours := _hours_between(c.get("opened_at"), c.get("closed_at"))) is not None
    ]

    return PlaybookStats(
        total_cases=len(cases),
        cases_open=sum(1 for c in cases if c["status"] == "open"),
        cases_in_flight=sum(1 for c in cases if c["status"] == "in_flight"),
        cases_recovered=len(recovered),
        recovery_rate=round(len(recovered) / len(cases), 4),
        amount_at_risk_cents=sum(int(c.get("amount_at_risk_cents") or 0) for c in cases),
        amount_recovered_cents=sum(int(c.get("amount_recovered_cents") or 0) for c in cases),
        avg_hours_to_recovery=round(sum(durations) / len(durations), 1) if durations else None,
    )


def _hours_between(opened: Any, closed: Any) -> float | None:
    if not opened or not closed:
        return None
    try:
        start = datetime.fromisoformat(str(opened))
        end = datetime.fromisoformat(str(closed))
    except (TypeError, ValueError):
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return max(0.0, (end - start).total_seconds() / 3600)


@router.get("")
async def list_playbooks(
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> dict[str, Any]:
    """All four playbooks with their live stats and on/off state.

    One read of the case table, grouped in memory, rather than four filtered
    reads. The four groups partition the same rows, so four queries would be
    four scans of the thing one scan already answers.
    """
    merchant = _merchant_row(supabase, user_id)
    config = dict(merchant.get("playbook_config") or {})

    cases = _rows(
        supabase.table("recovery_cases")
        .select(
            "playbook, status, amount_at_risk_cents, amount_recovered_cents, opened_at, closed_at"
        )
        .eq("merchant_id", user_id)
        .execute()
    )
    by_playbook: dict[str, list[dict[str, Any]]] = {slug: [] for slug in PLAYBOOK_CONFIGS}
    for case in cases:
        by_playbook.setdefault(str(case["playbook"]), []).append(case)

    return {
        "playbooks": [
            PlaybookSummary(
                slug=slug,
                label=PLAYBOOK_LABELS[slug],
                description=PLAYBOOK_DESCRIPTIONS[slug],
                enabled=is_enabled(config, slug),
                default_arm=cfg.default_arm,
                arm_count=len(cfg.arms),
                stats=_stats_for(by_playbook.get(slug, [])),
            ).model_dump(by_alias=True)
            for slug, cfg in PLAYBOOK_CONFIGS.items()
        ]
    }


@router.get("/{slug}")
async def get_playbook(
    slug: str,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> dict[str, Any]:
    """One playbook: its envelope, its stats, and its most recent cases."""
    _require_known(slug)
    config = get_playbook_config(slug)
    merchant = _merchant_row(supabase, user_id)

    cases = _rows(
        supabase.table("recovery_cases")
        .select(
            "playbook, status, amount_at_risk_cents, amount_recovered_cents, opened_at, closed_at"
        )
        .eq("merchant_id", user_id)
        .eq("playbook", slug)
        .execute()
    )

    recent = _rows(
        supabase.table("recovery_cases")
        .select(
            "id, status, playbook, amount_at_risk_cents, amount_recovered_cents, "
            "opened_at, closed_at, current_step, uplift_bucket, customers(name, email)"
        )
        .eq("merchant_id", user_id)
        .eq("playbook", slug)
        .order("opened_at", desc=True)
        .limit(10)
        .execute()
    )

    return {
        "slug": slug,
        "label": PLAYBOOK_LABELS[slug],
        "description": PLAYBOOK_DESCRIPTIONS[slug],
        "enabled": is_enabled(dict(merchant.get("playbook_config") or {}), slug),
        "stats": _stats_for(cases).model_dump(by_alias=True),
        # The whole envelope, so the page can show what the agent is allowed to
        # do rather than only what it did.
        "config": {
            "arms": config.arms,
            "default_arm": config.default_arm,
            "max_total_attempts": config.max_total_attempts,
            "max_messages_per_day": config.max_messages_per_day,
            "max_messages_per_week": config.max_messages_per_week,
            "max_discount_pct": config.max_discount_pct,
            "rbi_max_retries_per_cycle": config.rbi_max_retries_per_cycle,
            "rbi_min_hours_between_retries": config.rbi_min_hours_between_retries,
            "hard_stop_after_days": config.hard_stop_after_days,
            "channels_allowed": config.channels_allowed,
            "human_escalation_after_attempts": config.human_escalation_after_attempts,
        },
        "recent_cases": recent,
    }


@router.patch("/{slug}/toggle")
async def toggle_playbook(
    slug: str,
    user_id: CurrentUserId,
    supabase: UserSupabase,
) -> ToggleResponse:
    """Flip this playbook on or off for the signed-in merchant.

    Read-modify-write on one JSONB column. Not atomic, which is fine for a
    switch a human flips: the last click wins, and there is no interleaving that
    produces a state nobody asked for.

    Turning a playbook off does not touch cases already in flight. Those were
    opened under the old setting and closing them here would be a destructive
    side effect of a settings change — the switch governs what opens next.
    """
    _require_known(slug)
    merchant = _merchant_row(supabase, user_id)
    config = dict(merchant.get("playbook_config") or {})

    entry = config.get(slug)
    current = is_enabled(config, slug)
    # Preserve any other keys under this slug — a later phase will put per-
    # playbook overrides here and a toggle must not drop them.
    config[slug] = {**(entry if isinstance(entry, dict) else {}), "enabled": not current}

    supabase.table("merchants").update(
        {"playbook_config": config, "updated_at": datetime.now(UTC).isoformat()}
    ).eq("id", user_id).execute()

    log.info("playbook_toggled", merchant_id=user_id, playbook=slug, enabled=not current)
    return ToggleResponse(slug=slug, enabled=not current)
