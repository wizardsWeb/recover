"""Step 5 — Guardrail: the deterministic veto.

Every other step in the loop is a model, a stub, or a model-shaped hole. This
one is neither, and must never become one. It is the module that answers "was
Recover allowed to send that?" to a regulator, a merchant, or a customer who
complained — and the only defensible answer is a rule that ran the same way
every time, with its inputs and outputs written down.

Three sources of rules meet here:

* **RBI** — recurring-mandate limits: at most three retries per billing cycle,
  at least 24 hours between them. Breaking these risks the mandate itself.
* **TRAI** — commercial-communication limits: no promotional messaging between
  9pm and 9am IST, and per-merchant frequency caps.
* **Merchant policy** — the caps in ``PlaybookConfig``: total attempts, discount
  ceiling, how long to keep trying at all.

Design rules for anything added below:

1. **A check never guesses.** Missing data means the check records why it could
   not run and passes; it does not invent a value. A guardrail that blocks on
   absent metadata would silently abandon recoveries.
2. **The first BLOCK wins and stops.** Ordering is by severity, not cost:
   opt-out is checked before quiet hours because "never contact me" outranks
   "not right now", and the reason surfaced to the merchant should be the most
   fundamental one.
3. **Every check that ran is recorded**, passing or not. The list is the audit
   artefact; the verdict is just its summary.
"""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.agent.models import GuardrailCheckResult, GuardrailResult
from app.agent.playbooks import get_playbook_config
from app.logging import get_logger

IST = ZoneInfo("Asia/Kolkata")
logger = get_logger(__name__)

TRAI_QUIET_START_HOUR = 21  # 9 PM IST
TRAI_QUIET_END_HOUR = 9  # 9 AM IST

#: Actions that put a message in front of a human. Everything TRAI governs, and
#: everything that needs channel consent, is in this set — a silent retry is
#: neither a communication nor an interruption.
MESSAGE_ACTIONS = frozenset({"send_whatsapp", "send_sms", "send_email", "send_payment_link"})


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse a PostgREST timestamp into an aware UTC datetime.

    PostgREST hands back ISO 8601, but whether it carries an offset depends on
    the column type and the driver version. Subtracting a naive datetime from
    an aware one raises ``TypeError``, and a ``TypeError`` in here would take
    down the compliance path — so a naive value is read as UTC (which is what
    ``TIMESTAMPTZ`` stores) and an unparseable one yields ``None`` for the
    caller to treat as "no data".
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _blocked(
    checks: list[GuardrailCheckResult],
    blocking_check: str,
    case_id: str,
) -> GuardrailResult:
    """Build a BLOCK verdict and log it.

    Blocks are the interesting event in this module — a merchant asking "why did
    nothing go out?" is answered from these lines before anyone opens the audit
    table.
    """
    reason = next((c.reason for c in checks if c.check_name == blocking_check), None)
    logger.info("guardrail_blocked", case_id=case_id, check=blocking_check, reason=reason)
    return GuardrailResult(verdict="BLOCK", checks=checks, blocking_check=blocking_check)


async def run_guardrail(
    case: dict[str, Any],
    decision: dict[str, Any],
    customer: dict[str, Any],
    supabase_client: Any,
) -> GuardrailResult:
    """Run all compliance and merchant-policy checks.

    Returns PASS, BLOCK, or DOWNGRADE. All checks run independently; the first
    BLOCK stops processing.
    """
    checks: list[GuardrailCheckResult] = []
    case_id = case["id"]
    playbook_name = case["playbook"]
    config = get_playbook_config(playbook_name)
    action_type = decision.get("action_type", "no_op")
    now_ist = datetime.now(IST)

    # ─── CHECK 1: Explicit opt-out ───────────────────────────────────────
    # Outranks everything. A customer who said STOP is not a frequency problem
    # to be scheduled around; there is no hour at which contact becomes legal.
    consent = customer.get("consent") or {}
    opted_out = consent.get("opted_out_at") is not None
    checks.append(
        GuardrailCheckResult(
            check_name="explicit_opt_out",
            passed=not opted_out,
            reason="Customer has opted out of all communications" if opted_out else None,
        )
    )
    if opted_out:
        return _blocked(checks, "explicit_opt_out", case_id)

    # ─── CHECK 2: TRAI quiet hours (only for message-sending actions) ────
    is_message_action = action_type in MESSAGE_ACTIONS
    if is_message_action:
        hour = now_ist.hour
        in_quiet_hours = hour >= TRAI_QUIET_START_HOUR or hour < TRAI_QUIET_END_HOUR
        checks.append(
            GuardrailCheckResult(
                check_name="trai_quiet_hours",
                passed=not in_quiet_hours,
                reason=(
                    f"Current hour {hour}:00 IST is within TRAI quiet window "
                    f"({TRAI_QUIET_START_HOUR}:00-{TRAI_QUIET_END_HOUR}:00)"
                )
                if in_quiet_hours
                else None,
            )
        )
        if in_quiet_hours:
            return _blocked(checks, "trai_quiet_hours", case_id)
    else:
        checks.append(
            GuardrailCheckResult(
                check_name="trai_quiet_hours",
                passed=True,
                reason="Not a messaging action — quiet hours check skipped",
            )
        )

    # ─── CHECK 3: TRAI daily message frequency ───────────────────────────
    # The day boundary is IST midnight, not UTC midnight: the limit exists to
    # protect a person's day, and that person is in India.
    if is_message_action:
        today_start = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start.astimezone(UTC).isoformat()
        response = (
            supabase_client.table("execution_attempts")
            .select("id", count="exact")
            .eq("case_id", case_id)
            .in_("action_type", sorted(MESSAGE_ACTIONS))
            .eq("status", "success")
            .gte("attempted_at", today_start_utc)
            .execute()
        )
        msgs_today = response.count or 0
        daily_limit = config.max_messages_per_day
        checks.append(
            GuardrailCheckResult(
                check_name="trai_daily_message_limit",
                passed=msgs_today < daily_limit,
                reason=f"Already sent {msgs_today}/{daily_limit} messages today"
                if msgs_today >= daily_limit
                else None,
            )
        )
        if msgs_today >= daily_limit:
            return _blocked(checks, "trai_daily_message_limit", case_id)
    else:
        checks.append(
            GuardrailCheckResult(
                check_name="trai_daily_message_limit",
                passed=True,
                reason="Not a messaging action",
            )
        )

    # ─── CHECK 4: RBI mandate retry count (subscription only) ───────────
    if playbook_name == "subscription_failure" and action_type == "retry_charge":
        cycle_start = now_ist.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cycle_start_utc = cycle_start.astimezone(UTC).isoformat()
        resp = (
            supabase_client.table("execution_attempts")
            .select("id", count="exact")
            .eq("case_id", case_id)
            .eq("action_type", "retry_charge")
            .eq("status", "success")
            .gte("attempted_at", cycle_start_utc)
            .execute()
        )
        retries_this_cycle = resp.count or 0
        rbi_limit = config.rbi_max_retries_per_cycle
        checks.append(
            GuardrailCheckResult(
                check_name="rbi_mandate_retry_count",
                passed=retries_this_cycle < rbi_limit,
                reason=f"RBI limit: already {retries_this_cycle}/{rbi_limit} retries this cycle"
                if retries_this_cycle >= rbi_limit
                else None,
            )
        )
        if retries_this_cycle >= rbi_limit:
            return _blocked(checks, "rbi_mandate_retry_count", case_id)
    else:
        checks.append(
            GuardrailCheckResult(
                check_name="rbi_mandate_retry_count", passed=True, reason="Not applicable"
            )
        )

    # ─── CHECK 5: RBI minimum hours between retries ──────────────────────
    # Unlike check 4 this applies to every playbook, because the spacing rule is
    # about the issuer's tolerance for repeat authorisation, not about mandates.
    if action_type == "retry_charge":
        resp = (
            supabase_client.table("execution_attempts")
            .select("attempted_at")
            .eq("case_id", case_id)
            .eq("action_type", "retry_charge")
            .order("attempted_at", desc=True)
            .limit(1)
            .execute()
        )
        last_retry = _parse_timestamp(resp.data[0]["attempted_at"]) if resp.data else None
        if last_retry is not None:
            hours_since = (datetime.now(UTC) - last_retry).total_seconds() / 3600
            min_hours = config.rbi_min_hours_between_retries
            checks.append(
                GuardrailCheckResult(
                    check_name="rbi_min_hours_between_retries",
                    passed=hours_since >= min_hours,
                    reason=(f"Only {hours_since:.1f}h since last retry; RBI requires {min_hours}h")
                    if hours_since < min_hours
                    else None,
                )
            )
            if hours_since < min_hours:
                return _blocked(checks, "rbi_min_hours_between_retries", case_id)
        else:
            checks.append(
                GuardrailCheckResult(
                    check_name="rbi_min_hours_between_retries",
                    passed=True,
                    reason="No previous retry",
                )
            )
    else:
        checks.append(
            GuardrailCheckResult(
                check_name="rbi_min_hours_between_retries",
                passed=True,
                reason="Not a retry action",
            )
        )

    # ─── CHECK 6: Max total attempts ─────────────────────────────────────
    resp = (
        supabase_client.table("execution_attempts")
        .select("id", count="exact")
        .eq("case_id", case_id)
        .neq("action_type", "no_op")
        .execute()
    )
    total_attempts = resp.count or 0
    max_attempts = config.max_total_attempts
    checks.append(
        GuardrailCheckResult(
            check_name="max_total_attempts",
            passed=total_attempts < max_attempts,
            reason=f"Case has reached maximum {max_attempts} attempts"
            if total_attempts >= max_attempts
            else None,
        )
    )
    if total_attempts >= max_attempts:
        return _blocked(checks, "max_total_attempts", case_id)

    # ─── CHECK 7: Hard stop after N days ─────────────────────────────────
    # Past the window the money is gone and the only thing left to lose is the
    # relationship. Stopping is the correct recovery strategy.
    opened_at = _parse_timestamp(case.get("opened_at"))
    if opened_at is not None:
        days_open = (datetime.now(UTC) - opened_at).days
        hard_stop = config.hard_stop_after_days
        checks.append(
            GuardrailCheckResult(
                check_name="hard_stop_after_days",
                passed=days_open < hard_stop,
                reason=f"Case open for {days_open} days, exceeds {hard_stop}-day limit"
                if days_open >= hard_stop
                else None,
            )
        )
        if days_open >= hard_stop:
            return _blocked(checks, "hard_stop_after_days", case_id)
    else:
        checks.append(GuardrailCheckResult(check_name="hard_stop_after_days", passed=True))

    # ─── CHECK 8: Channel consent ─────────────────────────────────────────
    # The only check that can DOWNGRADE rather than block: no consent for
    # WhatsApp is not a reason to abandon the recovery if the customer has
    # opted in to email.
    if is_message_action:
        channel = (decision.get("action_params") or {}).get("channel", "whatsapp")
        has_consent = consent.get(channel, False)
        checks.append(
            GuardrailCheckResult(
                check_name="channel_consent",
                passed=bool(has_consent),
                reason=f"Customer has not opted in to {channel}" if not has_consent else None,
            )
        )
        if not has_consent:
            # Downgrade: try next channel in config.channels_allowed
            allowed = config.channels_allowed
            idx = allowed.index(channel) if channel in allowed else -1
            downgrade_channel = allowed[idx + 1] if idx + 1 < len(allowed) else None
            if downgrade_channel:
                logger.info(
                    "guardrail_downgraded",
                    case_id=case_id,
                    from_channel=channel,
                    to_channel=downgrade_channel,
                )
                return GuardrailResult(
                    verdict="DOWNGRADE",
                    checks=checks,
                    blocking_check="channel_consent",
                    downgrade_to=f"switch_to_{downgrade_channel}",
                )
            return _blocked(checks, "channel_consent", case_id)
    else:
        checks.append(
            GuardrailCheckResult(
                check_name="channel_consent", passed=True, reason="Not a messaging action"
            )
        )

    # ─── CHECK 9: Network alert (bank degradation) ────────────────────────
    # Retrying into a bank that is down burns an RBI-limited retry on a
    # certainty. The network view is the whole point of a multi-merchant agent:
    # no single merchant sees enough failures to call an outage.
    if action_type == "retry_charge":
        metadata = case.get("metadata") or {}
        bank = metadata.get("bank") or ""
        method = metadata.get("method") or ""
        if bank and method:
            resp = (
                supabase_client.table("network_alerts")
                .select("id")
                .eq("affected_bank", bank.upper())
                .eq("affected_method", method.lower())
                .is_("resolved_at", "null")
                .limit(1)
                .execute()
            )
            in_downtime = bool(resp.data)
            checks.append(
                GuardrailCheckResult(
                    check_name="network_bank_health",
                    passed=not in_downtime,
                    reason=f"Active network alert for {bank} {method} — pausing retries"
                    if in_downtime
                    else None,
                )
            )
            if in_downtime:
                return _blocked(checks, "network_bank_health", case_id)
        else:
            checks.append(
                GuardrailCheckResult(
                    check_name="network_bank_health",
                    passed=True,
                    reason="Bank/method not in case metadata",
                )
            )
    else:
        checks.append(
            GuardrailCheckResult(
                check_name="network_bank_health", passed=True, reason="Not a retry action"
            )
        )

    # All checks passed
    return GuardrailResult(verdict="PASS", checks=checks)
