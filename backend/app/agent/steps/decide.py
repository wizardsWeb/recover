"""Step 4 — Decide: which arm do we play?

Phase 4 plays the playbook's ``default_arm`` every time. That choice is not
arbitrary: each default is the most conservative arm in its action space —
a silent retry, a no-discount message, a polite tone — so a stub decision can
never spend margin or goodwill that the bandit has not yet earned the right to
spend.

The result still carries a full ``alternatives_considered`` list. A decision is
only explainable against the options it beat, and building that habit now means
Phase 6 has somewhere to put real posterior draws rather than bolting the
counterfactual on afterwards.
"""

from typing import Any

from app.agent.models import (
    ActionType,
    BanditAlternative,
    DecisionResult,
    DecisionSource,
)
from app.agent.playbooks import get_default_action_params, get_playbook_config

#: Arm name -> the physical action it resolves to.
#:
#: NOTE — this diverges from ``bandit_arms.action_type`` in the Phase 2 seed for
#: the five link-delivery arms below, which the migration types as
#: ``send_payment_link`` and this map types by delivery channel:
#:
#:   whatsapp_payment_link, sms_payment_link, email_payment_link,
#:   switch_method_upi, whatsapp_payment_link_now
#:
#: None of them is a ``default_arm``, so nothing in Phase 4 exercises the
#: difference. Phase 6 must pick one source of truth before the bandit can
#: select them — see the Phase 4 handover notes.
ARM_TO_ACTION_TYPE: dict[str, ActionType] = {
    "retry_now": ActionType.RETRY_CHARGE,
    "retry_at_optimal_hour": ActionType.RETRY_CHARGE,
    "silent_retry_next_morning": ActionType.RETRY_CHARGE,
    "retry_at_inferred_date": ActionType.RETRY_CHARGE,
    "retry_at_inferred_date_plus_whatsapp_fallback": ActionType.RETRY_CHARGE,
    "immediate_retry": ActionType.RETRY_CHARGE,
    "whatsapp_payment_link": ActionType.SEND_WHATSAPP,
    "whatsapp_payment_link_now": ActionType.SEND_WHATSAPP,
    "whatsapp_saved_cart_no_discount": ActionType.SEND_WHATSAPP,
    "whatsapp_saved_cart_5pct": ActionType.SEND_WHATSAPP,
    "whatsapp_saved_cart_8pct": ActionType.SEND_WHATSAPP,
    "whatsapp_saved_cart_12pct": ActionType.SEND_WHATSAPP,
    "polite_reminder_whatsapp": ActionType.SEND_WHATSAPP,
    "firm_reminder_whatsapp": ActionType.SEND_WHATSAPP,
    "firm_reminder_whatsapp_plus_email": ActionType.SEND_WHATSAPP,
    "partial_payment_offer": ActionType.SEND_PAYMENT_LINK,
    "payment_plan_offer": ActionType.SEND_PAYMENT_LINK,
    "sms_payment_link": ActionType.SEND_SMS,
    "sms_saved_cart": ActionType.SEND_SMS,
    "email_payment_link": ActionType.SEND_EMAIL,
    "email_saved_cart": ActionType.SEND_EMAIL,
    "dunning_email_sequence": ActionType.SEND_EMAIL,
    # Seeded in the b2b_overdue action space but absent from the Phase 4 spec's
    # table; without it the arm would silently resolve to no_op.
    "polite_reminder_email": ActionType.SEND_EMAIL,
    "switch_method_upi": ActionType.SEND_WHATSAPP,
    "mandate_reregistration": ActionType.MANDATE_REREGISTER,
    "human_handoff": ActionType.HUMAN_HANDOFF,
    "escalate_to_human_ar": ActionType.HUMAN_HANDOFF,
    "pause_with_winback": ActionType.NO_OP,
    "accept_promise_to_pay": ActionType.NO_OP,
    "graduated_b2b_sequence": ActionType.SEND_WHATSAPP,
    "no_op": ActionType.NO_OP,
    "suggest_alternate_method": ActionType.SEND_WHATSAPP,
}

_STUB_NOT_CHOSEN_REASON = "Stub decision — bandit not yet wired (Phase 6)"


async def run_decide(
    case: dict[str, Any],
    diagnosis: dict[str, Any],
    playbook: str,
) -> DecisionResult:
    """Pick the ``default_arm`` from the PlaybookConfig.

    Phase 6 replaces this with contextual bandit selection over the same arm
    list, at which point ``decision_source`` becomes ``bandit`` and
    ``bandit_mode`` starts distinguishing exploit from explore.
    """
    config = get_playbook_config(playbook)
    chosen_arm = config.default_arm
    action_type = ARM_TO_ACTION_TYPE.get(chosen_arm, ActionType.NO_OP)

    # Build alternatives list showing other arms considered (stub shows all arms).
    alternatives = [
        BanditAlternative(
            arm_name=arm,
            expected_reward=0.5 if arm == chosen_arm else 0.3,
            chosen=(arm == chosen_arm),
            not_chosen_reason=None if arm == chosen_arm else _STUB_NOT_CHOSEN_REASON,
        )
        for arm in config.arms
    ]

    return DecisionResult(
        chosen_arm=chosen_arm,
        action_type=action_type,
        # Per-arm params rather than one hard-coded dict: the guardrail's channel
        # consent check reads `action_params["channel"]`, so a retry arm that
        # claimed a WhatsApp channel would be checked against consent it never
        # needed.
        action_params=get_default_action_params(playbook, chosen_arm),
        decision_source=DecisionSource.RULE,
        arm_confidence=0.5,
        expected_recovery_probability=0.5,
        alternatives_considered=alternatives,
        reasoning=(
            f"Rule-based default arm '{chosen_arm}' selected. "
            "Contextual bandit (Phase 6) will replace this."
        ),
        is_stub=True,
    )
