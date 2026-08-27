"""Closing the loop: turning a case outcome into a posterior update.

The bandit only learns if outcomes get back to the arm that caused them. This
module is that path, and it runs once per case close.

**It reads the decision rather than being told the arm.** The arm and the
context vector are fetched from the ``agent_decisions`` row written at decide
time, not passed down through the loop. That matters because the reward has to
land on the posterior the decision was actually drawn from: if the context were
recomputed now, a case that closed on a different day — or after a downgrade
rewrote the channel — would credit an arm in a bucket it was never played in,
and the bandit would learn from an experiment it did not run.

**Two rewards are recorded, deliberately.** The posterior takes a *binary*
reward, because Beta-Bernoulli is a model of "did this work", and feeding it a
fraction would quietly turn alpha into something that is no longer a count. The
``bandit_rewards`` log separately stores the *amount-normalised* value, which is
the number the money-weighted analysis in Phase 11 needs. Same event, two
readings, neither pretending to be the other.

Holdout cases are skipped entirely. A holdout is the control group for Phase 9's
uplift model — the agent deliberately did nothing — so there is no arm to credit
and folding it in would bias every posterior toward the do-nothing outcome.
"""

from typing import Any

from app.agent.bandit.context import make_context_bucket
from app.agent.bandit.thompson import update_posterior
from app.logging import get_logger

logger = get_logger(__name__)

#: The one status that counts as a win for the binary reward.
RECOVERED_STATUS = "recovered"

#: Cases in the uplift control group. Never rewarded — see the module docstring.
HOLDOUT_STATUS = "holdout"


async def post_reward(
    supabase_client: Any,
    case: dict[str, Any],
    final_status: str,
    trace_id: str,
) -> None:
    """Credit the chosen arm with this case's outcome. Never raises.

    Called after the case reaches a terminal state. Everything is wrapped: the
    pass that calls this has already done its useful work, and a statistics
    write must not be able to undo it.
    """
    case_id = str(case.get("id") or "")
    merchant_id = str(case.get("merchant_id") or "")
    log = logger.bind(case_id=case_id, trace_id=trace_id)

    if not case_id or not merchant_id:
        log.warning("reward_skipped_incomplete_case")
        return

    if final_status == HOLDOUT_STATUS or case.get("status") == HOLDOUT_STATUS:
        log.info("reward_skipped_holdout")
        return

    try:
        decision = _fetch_decide_row(supabase_client, case_id)
        if not decision:
            log.info("reward_skipped_no_decision")
            return

        arm_name = decision.get("bandit_chosen_arm")
        if not arm_name:
            log.info("reward_skipped_no_arm")
            return

        context_vector = decision.get("bandit_context_vector") or {}
        # Derived from the stored vector, never recomputed from the case — see
        # the module docstring. An older decision with no vector falls back to
        # the same "unknown everything" bucket `make_context_bucket` would give
        # it, which is at least consistent.
        context_bucket = make_context_bucket(context_vector)

        binary_reward = 1.0 if final_status == RECOVERED_STATUS else 0.0
        playbook = str(case.get("playbook") or "")

        await update_posterior(
            supabase_client,
            merchant_id,
            playbook,
            str(arm_name),
            context_bucket,
            binary_reward,
        )

        _log_reward_row(
            supabase_client,
            merchant_id=merchant_id,
            case_id=case_id,
            decision_id=decision.get("id"),
            arm_name=str(arm_name),
            context_vector=context_vector,
            context_bucket=context_bucket,
            reward_value=_amount_normalised_reward(case),
        )

        log.info(
            "reward_posted",
            arm=arm_name,
            bucket=context_bucket,
            binary_reward=binary_reward,
            final_status=final_status,
        )
    except Exception as exc:  # noqa: BLE001 - learning must never break a closed case
        log.warning("reward_post_error", error=str(exc))


def _fetch_decide_row(supabase_client: Any, case_id: str) -> dict[str, Any] | None:
    """The decide-step decision for this case, or ``None``.

    Ordered newest-first: a case worked over several passes has several decide
    rows, and the outcome belongs to the arm most recently played, not the first
    one tried.
    """
    resp = (
        supabase_client.table("agent_decisions")
        .select("id, bandit_chosen_arm, bandit_context_vector")
        .eq("case_id", case_id)
        .eq("step_name", "decide")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return dict(resp.data[0]) if resp.data else None


def _amount_normalised_reward(case: dict[str, Any]) -> float:
    """Fraction of the money at risk that came back, clamped to [0, 1].

    A partial payment is a partial win and the money-weighted view should say
    so. Clamped because a customer can pay more than the case tracked — a
    rounded-up invoice, an unrelated charge landing in the same window — and a
    reward above 1 would be meaningless.
    """
    at_risk = int(case.get("amount_at_risk_cents") or 0)
    recovered = int(case.get("amount_recovered_cents") or 0)
    if at_risk <= 0:
        return 0.0
    return min(1.0, max(0.0, recovered / at_risk))


def _log_reward_row(
    supabase_client: Any,
    *,
    merchant_id: str,
    case_id: str,
    decision_id: Any,
    arm_name: str,
    context_vector: dict[str, Any],
    context_bucket: str,
    reward_value: float,
) -> None:
    """Append the observation to ``bandit_rewards``.

    Separate from the posterior update on purpose: the posterior is a running
    summary that can be recomputed, and this is the immutable event log it would
    be recomputed *from*. Losing the log costs the ability to re-derive; losing
    the summary costs nothing permanent.
    """
    try:
        supabase_client.table("bandit_rewards").insert(
            {
                "merchant_id": merchant_id,
                "case_id": case_id,
                "decision_id": decision_id,
                "arm_name": arm_name,
                "context_vector": context_vector,
                "context_bucket": context_bucket,
                "reward_value": reward_value,
                "reward_type": "amount_normalized",
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("bandit_reward_log_error", case_id=case_id, error=str(exc))
