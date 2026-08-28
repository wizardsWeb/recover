"""The ground truth the batch simulator is asked to rediscover.

A learning curve is only worth drawing if there is something real to learn. This
module is that something: a hidden number per arm saying how much better or
worse it is than doing the obvious thing, and a base rate per playbook saying
how often a customer would have paid anyway.

The bandit never sees any of it. It observes outcomes drawn from these numbers
and has to infer the ranking from scratch, which is exactly the task it performs
in production against a world that also declines to show its parameters. If the
curve bends, the algorithm found the ordering below.

**How the numbers were chosen.** Backwards, from the targets in `scenarios.md`:

    effective recovery probability = base_twp x lift_factor

`base_twp` is the probability a customer pays given an intervention of *average*
quality, so 1.0 is the average arm and not the default one. The default arm sits
below it, between 0.69 and 0.96 depending on playbook, and that is the honest
place for it: it is a rule someone wrote without evidence, so it should be
respectable and beatable rather than either a strawman or unbeatable. Its lift
is fixed by the target — `baseline_rate / base_twp` — and the top arm's follows
from the settled bandit rate, discounted for the fact that Thompson sampling
never stops exploring and so never plays the best arm every time.

The values below were then checked by running the batch; see `_CALIBRATION` at
the bottom for the measured result and `tests/simulator/test_batch_calibration`
for the assertion that keeps them honest.

**Two separate rates, easy to confuse.** `_BASE_TWP` is what an intervention
achieves. `TRUE_WILLINGNESS_TO_PAY_BASE` is what happens with *no* intervention
at all — the counterfactual the uplift number is measured against. Failed
payments self-heal often (a card that failed at 2am works at 9am); an abandoned
cart almost never does. The gap between them is the only thing the agent can
honestly claim to have caused, and it is why gross and incremental differ so
much on the ROI page.

The spread within a playbook encodes a claim about the world, not a random
draw. Subscription failures respond to *timing* — retrying on the inferred
salary date beats retrying immediately by a wide margin, which is scenario S1's
whole thesis. Checkout abandonment responds to *discount depth*, with
diminishing returns that turn negative once the discount costs more margin than
the recovery is worth. B2B responds to *escalation*, slowly.
"""

from __future__ import annotations

#: Probability a customer recovers given an average-quality intervention.
#: Multiplied by an arm's lift factor to get that arm's true success rate.
BASE_TWP: dict[str, float] = {
    "subscription_failure": 0.35,
    "checkout_abandonment": 0.25,
    "failed_payment": 0.30,
    "b2b_overdue": 0.22,
}

#: Probability a customer recovers with **no** intervention at all.
#:
#: The counterfactual. Anything at or below this line the agent did not cause,
#: however much money arrived afterwards — the distinction the whole uplift
#: model exists to draw, here stated as a parameter because a simulation is the
#: one place the counterfactual is actually knowable.
#:
#: **These are rescaled from the figures in the phase plan, which cannot be used
#: as written.** It quotes self-heal rates of 0.34 for `failed_payment` and 0.28
#: for `b2b_overdue` alongside target recovery rates of 0.38 and 0.28 and a
#: baseline of 0.22 — so on its own numbers the untouched customer pays more
#: often than the contacted one, incremental revenue comes out negative, and the
#: results screen reports the agent destroying value. The ordering the plan
#: intends is kept exactly (failed payments self-heal most often, an abandoned
#: cart almost never does) and every rate is scaled by 0.47, which puts
#: incremental at roughly 60% of gross — the "true attribution" figure the
#: results screen was specified to show.
TRUE_WILLINGNESS_TO_PAY_BASE: dict[str, float] = {
    "subscription_failure": 0.10,
    "checkout_abandonment": 0.04,
    "failed_payment": 0.16,
    "b2b_overdue": 0.13,
}

#: Rupees an intervention costs to send, by action shape. Message costs are
#: Indian list prices; a retry costs nothing until it settles; a human handoff
#: is priced as twenty minutes of an AR clerk's time, which is what makes
#: `escalate_to_human_ar` a genuinely expensive arm rather than a free one.
INTERVENTION_COST_INR: dict[str, float] = {
    "whatsapp": 0.35,
    "sms": 0.20,
    "email": 0.01,
    "retry": 0.00,
    "human": 150.00,
    "none": 0.00,
}

#: How much better or worse each arm is than an average intervention.
#:
#: **The mean arm sits at roughly the default arm's level, and that is the whole
#: shape of the learning curve.** If the average arm beat the default, a bandit
#: playing at random would already be ahead and the curve would start above the
#: baseline — there would be no exploration cost to show, and the claim that
#: learning is worth paying for would be unfalsifiable. Tuned so a fresh bandit
#: trails for roughly the first two hundred cases and then pulls away, which is
#: what the measured convergence points below confirm.
#:
#: `no_op` is deliberately not zero. Some customers pay unprompted, and an arm
#: that recovered nothing at all would be trivially identifiable after two
#: pulls — the interesting case is the arm that looks passable and is not.
ARM_LIFT_FACTORS: dict[str, dict[str, float]] = {
    # S1's thesis, as numbers: *when* you retry a failed mandate matters more
    # than what you say about it. Inferring the salary date is the win; retrying
    # immediately into an empty account is the trap that looks like diligence.
    "subscription_failure": {
        "retry_at_inferred_date_plus_whatsapp_fallback": 1.89,
        "retry_at_inferred_date": 0.73,  # default
        "human_handoff": 0.50,
        "whatsapp_payment_link_now": 0.45,
        "mandate_reregistration": 0.39,
        "dunning_email_sequence": 0.30,
        "immediate_retry": 0.25,
        "pause_with_winback": 0.19,
    },
    # Discount depth with diminishing returns. 12% recovers barely more than 8%
    # while costing half again as much margin — the kind of arm a bandit
    # optimising a rate is happy to pick and a merchant is not, which is why the
    # playbook caps discount depth rather than trusting the ranking.
    "checkout_abandonment": {
        "whatsapp_saved_cart_12pct": 1.87,
        "whatsapp_saved_cart_8pct": 1.85,
        "whatsapp_saved_cart_5pct": 1.43,
        "whatsapp_saved_cart_no_discount": 0.85,  # default
        "suggest_alternate_method": 0.47,
        "sms_saved_cart": 0.37,
        "email_saved_cart": 0.29,
        "no_op": 0.14,
    },
    # Timing again, and the finding the network heatmap shows independently:
    # the optimal hour beats both an instant retry and a blind next-morning one.
    "failed_payment": {
        "retry_at_optimal_hour": 1.71,
        "switch_method_upi": 1.45,
        "whatsapp_payment_link": 1.22,
        "silent_retry_next_morning": 0.82,  # default
        "sms_payment_link": 0.39,
        "retry_now": 0.34,
        "email_payment_link": 0.30,
        "no_op": 0.16,
    },
    # Escalation works on businesses, slowly, and a payment plan beats a firmer
    # tone. The human arm is nearly as effective as the best one and four hundred
    # times more expensive — the cost-per-₹100 metric is the only place that
    # shows up, which is exactly why that metric is on the results screen.
    "b2b_overdue": {
        "payment_plan_offer": 1.99,
        "escalate_to_human_ar": 1.86,
        "partial_payment_offer": 1.79,
        "graduated_b2b_sequence": 1.51,
        "firm_reminder_whatsapp_plus_email": 1.33,
        "firm_reminder_whatsapp": 1.22,
        "polite_reminder_whatsapp": 1.02,  # default
        "polite_reminder_email": 0.41,
        "accept_promise_to_pay": 0.36,
    },
}

#: Fallback for an arm this table has not caught up with. Neutral rather than
#: zero: a new arm should be worth trying, not condemned by its own novelty.
DEFAULT_LIFT_FACTOR = 1.0

#: Which cost band each arm draws from, by the shape of what it sends.
_COST_BAND_PREFIXES: tuple[tuple[str, str], ...] = (
    ("whatsapp", "whatsapp"),
    ("sms", "sms"),
    ("email", "email"),
    ("dunning_email", "email"),
    ("retry", "retry"),
    ("immediate_retry", "retry"),
    ("silent_retry", "retry"),
    ("switch_method", "retry"),
    ("mandate_re", "retry"),
    ("human", "human"),
    ("escalate_to_human", "human"),
    ("no_op", "none"),
    ("accept_promise", "none"),
    ("pause_with", "none"),
)


def lift_factor(playbook: str, arm: str) -> float:
    """This arm's true multiplier on the playbook's base rate."""
    return ARM_LIFT_FACTORS.get(playbook, {}).get(arm, DEFAULT_LIFT_FACTOR)


def intervention_cost_inr(arm: str) -> float:
    """Rupees this arm costs to fire, before knowing whether it worked."""
    for prefix, band in _COST_BAND_PREFIXES:
        if arm.startswith(prefix):
            return INTERVENTION_COST_INR[band]
    # An arm nobody has priced. Charged as a message rather than as free — a
    # zero here would quietly flatter the cost-per-₹100 figure.
    return INTERVENTION_COST_INR["whatsapp"]


#: Measured over thirty 1,000-case runs, seeds 1-30. Reproduce with
#: `tests/simulator/test_batch_calibration.py`, which asserts these stay put.
#:
#: `settled` is the last quarter of the run — the converged policy, which is
#: what `scenarios.md` quotes. `whole` includes the exploration the bandit had
#: to pay for to get there, and is four to five points lower by definition.
#:
#: The per-playbook standard deviations are the reason the test is loose on
#: them: a thousand cases leaves 55 subscription and 20 B2B cases in the settled
#: window, so those rates swing about ten points run to run. Asserting a
#: three-point tolerance on a number with a ten-point spread would produce a
#: test that fails a third of the time and teaches nothing when it does.
_CALIBRATION = """
metric                  whole  settled  target   delta     sd
bandit                  0.337    0.389   0.380  +0.009  0.032
baseline                0.223    0.221   0.220  +0.001  0.027
subscription_failure    0.377    0.474   0.420  +0.054  0.087
checkout_abandonment    0.293    0.340   0.310  +0.030  0.052
failed_payment          0.352    0.392   0.380  +0.012  0.058
b2b_overdue             0.314    0.330   0.280  +0.050  0.112

incremental / gross        0.606   (results screen reads ~60% true attribution)
convergence case, median     175   (crossover inside the 150-300 window)
"""
