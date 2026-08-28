"""Step 4 — Decide: which arm do we play?

A Thompson Sampling contextual bandit picks the arm. It draws one sample from
every arm's Beta posterior for this case's context bucket and plays the highest
draw; the full ranking, each arm's draw, and each arm's mean are recorded so the
decision is explainable against the options it beat rather than only asserted.

**The rule-based default is now the fallback, not the policy.** Every playbook's
``default_arm`` is the most conservative arm in its action space — a silent
retry, a no-discount message, a polite tone — so when the bandit path fails the
agent falls back to something that cannot spend margin or goodwill it has not
earned. That path sets ``decision_source = RULE``, and the audit trail
distinguishes the two, so a bandit choice is never mistaken for a rule and vice
versa.

One distinction worth being precise about: **an empty posterior map is not a
failure.** A context nobody has played yet returns ``{}`` from
``fetch_posteriors``, every arm takes the flat prior, and the bandit explores —
which is correct behaviour, not degraded behaviour. Only an actual exception
drops to the rule path.
"""

from typing import Any

from app.agent.bandit.context import (
    extract_context_vector,
    get_arm_reasoning,
    make_context_bucket,
)
from app.agent.bandit.thompson import (
    ArmSample,
    fetch_posteriors,
    is_exploring,
    run_thompson_sampling,
)
from app.agent.models import (
    ActionType,
    BanditAlternative,
    DecisionResult,
    DecisionSource,
)
from app.agent.playbooks import (
    ARM_TO_ACTION_TYPE,
    get_default_action_params,
    get_playbook_config,
)
from app.logging import get_logger

logger = get_logger(__name__)


async def run_decide(
    case: dict[str, Any],
    diagnosis: dict[str, Any],
    playbook: str,
    supabase_client: Any = None,
    customer: dict[str, Any] | None = None,
    event: dict[str, Any] | None = None,
) -> DecisionResult:
    """Draw an arm from the posteriors for this case's context.

    ``supabase_client`` is optional so the step stays callable without a
    database; without one there are no posteriors, so every arm is at its prior
    and the choice is a uniform draw over the action space.
    """
    config = get_playbook_config(playbook)
    context = extract_context_vector(case, customer, event)
    context_bucket = make_context_bucket(context)

    if not config.arms:
        return _rule_fallback(playbook, context, "This playbook has no arms configured")

    try:
        posteriors = (
            await fetch_posteriors(
                supabase_client,
                str(case.get("merchant_id") or ""),
                playbook,
                context_bucket,
                config.arms,
            )
            if supabase_client is not None
            else {}
        )
        ranked = run_thompson_sampling(config.arms, posteriors)
    except Exception as exc:  # noqa: BLE001 - a broken bandit must still decide
        logger.warning("bandit_decide_failed", playbook=playbook, error=str(exc))
        return _rule_fallback(playbook, context, f"Bandit unavailable: {exc}")

    chosen = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    exploring = is_exploring(chosen, runner_up)

    logger.info(
        "bandit_arm_chosen",
        arm=chosen.arm_name,
        bucket=context_bucket,
        theta=round(chosen.sampled_theta, 4),
        expected=round(chosen.expected_win_rate, 4),
        mode="explore" if exploring else "exploit",
        n_pulls=chosen.n_pulls,
    )

    return DecisionResult(
        chosen_arm=chosen.arm_name,
        action_type=ARM_TO_ACTION_TYPE.get(chosen.arm_name, ActionType.NO_OP),
        # Per-arm params rather than one hard-coded dict: the guardrail's channel
        # consent check reads `action_params["channel"]`, so a retry arm that
        # claimed a WhatsApp channel would be checked against consent it never
        # needed.
        action_params=get_default_action_params(playbook, chosen.arm_name),
        decision_source=DecisionSource.BANDIT,
        bandit_mode="explore" if exploring else "exploit",
        arm_confidence=round(chosen.expected_win_rate, 3),
        expected_recovery_probability=round(chosen.expected_win_rate, 3),
        alternatives_considered=[_to_alternative(sample, chosen) for sample in ranked],
        reasoning=_build_reasoning(chosen, context, exploring, runner_up),
        bandit_context_vector=context,
        is_stub=False,
    )


def _to_alternative(sample: ArmSample, chosen: ArmSample) -> BanditAlternative:
    """One arm's row in the counterfactual, winner included."""
    is_chosen = sample.arm_name == chosen.arm_name
    return BanditAlternative(
        arm_name=sample.arm_name,
        # The posterior mean, not the draw: the bar a merchant reads should be
        # what the agent believes about this arm, not the die roll it happened
        # to get. The draw is alongside it for anyone checking the arithmetic.
        expected_reward=round(sample.expected_win_rate, 4),
        chosen=is_chosen,
        not_chosen_reason=None if is_chosen else _not_chosen_reason(sample, chosen),
        sampled_theta=round(sample.sampled_theta, 4),
        n_pulls=sample.n_pulls,
        is_cold=sample.is_cold,
    )


def _not_chosen_reason(sample: ArmSample, chosen: ArmSample) -> str:
    """Why this arm lost, in terms a merchant can check.

    An untried arm and a tried-and-worse arm lose for genuinely different
    reasons, and collapsing both into "lower score" would hide the one case
    where the agent is guessing.
    """
    if sample.is_cold:
        return (
            f"Never tried in this context — drew {sample.sampled_theta:.2f} "
            f"against {chosen.sampled_theta:.2f}"
        )
    return (
        f"{sample.expected_win_rate:.0%} recovery over {sample.n_pulls} past pulls "
        f"vs {chosen.expected_win_rate:.0%} for the chosen arm"
    )


def _build_reasoning(
    chosen: ArmSample,
    context: dict[str, Any],
    exploring: bool,
    runner_up: ArmSample | None,
) -> str:
    """The sentence written to the audit trail."""
    base = get_arm_reasoning(chosen.arm_name, context)

    if chosen.is_cold:
        evidence = "No history in this context yet — this pull is the first observation."
    else:
        evidence = (
            f"Posterior Beta({chosen.alpha:.0f}, {chosen.beta:.0f}) over "
            f"{chosen.n_pulls} pulls, mean {chosen.expected_win_rate:.0%}."
        )

    if exploring and runner_up is not None:
        mode = (
            f"Exploring: {runner_up.arm_name} has the higher mean "
            f"({runner_up.expected_win_rate:.0%}), but this arm's draw was higher, "
            "so this pull buys information about it."
        )
    else:
        mode = "Exploiting: this arm has both the best draw and the standing evidence."

    return f"{base} {evidence} {mode}"


def _rule_fallback(playbook: str, context: dict[str, Any], why: str) -> DecisionResult:
    """The conservative default arm, when the bandit cannot answer.

    Marked ``RULE`` rather than ``BANDIT`` so the analytics that compare the two
    do not count a fallback as a bandit decision and dilute the very measurement
    they exist to make. ``is_stub`` stays ``False``: a real decision was made,
    just not by the bandit.
    """
    config = get_playbook_config(playbook)
    chosen_arm = config.default_arm
    logger.warning("bandit_rule_fallback", playbook=playbook, arm=chosen_arm, reason=why)

    return DecisionResult(
        chosen_arm=chosen_arm,
        action_type=ARM_TO_ACTION_TYPE.get(chosen_arm, ActionType.NO_OP),
        action_params=get_default_action_params(playbook, chosen_arm),
        decision_source=DecisionSource.RULE,
        bandit_mode=None,
        alternatives_considered=[
            BanditAlternative(
                arm_name=arm,
                expected_reward=0.0,
                chosen=(arm == chosen_arm),
                not_chosen_reason=None if arm == chosen_arm else why,
            )
            for arm in config.arms
        ],
        reasoning=(
            f"Fell back to the conservative default arm '{chosen_arm}'. {why}. "
            f"Context: {make_context_bucket(context)}."
        ),
        bandit_context_vector=context,
        is_stub=False,
    )
