# Recover — submission narrative

## The problem

Every Razorpay merchant loses revenue that was already won. A card declines at
the bank, a cart dies at the OTP screen, an autopay mandate fails on the 1st
because the customer's salary lands on the 7th, a B2B invoice ages past ninety
days with a buyer who has never actually defaulted. The standard answer is a
dunning cron: retry three times, send everyone the same three reminders, count
whatever arrives afterwards as recovered. That over-messages the people who would
have paid anyway, under-serves the ones a different approach would have reached,
and reports a number that cannot tell the two apart.

## What Recover does differently

It treats each leak as a case to diagnose rather than a row to retry, and all
four of its judgements are inspectable.

**The diagnosis is a traversal, not a sentence.** A per-playbook causal DAG runs
Bayesian inference over the evidence, so "salary cycle mismatch · 0.82" is a
posterior over a named hypothesis rather than prose a model wrote.

**The decision names what it rejected.** A contextual Thompson bandit over bank,
method, hour and LTV band picks the arm, and the case shows every alternative
with its posterior and its draw. Exploration scales with uncertainty — no epsilon
to tune, no schedule to decay.

**The measurement is honest by construction.** A T-learner sorts customers into
persuadable, sure thing, lost cause and do-not-disturb, so the agent can decline
to spend a send on someone who would have paid regardless. One case in twenty is
held out untouched, which is what makes the headline figure incremental rather
than gross.

**The intelligence compounds across merchants.** Bank and method health is pooled
network-wide, so a merchant's first case in a context starts from what everyone
else learned about that bank an hour ago instead of from a flat prior.

## Why Razorpay

Recovery has to execute where the money already is — Payment Links,
Subscriptions, the Payment Gateway — and an agent one integration removed from
those rails can advise but not act. The deeper reason is the moat:
cross-merchant instrument health is only available to a party that sees every
merchant's retries. That is a position Razorpay holds and a standalone tool
cannot reach.

## Results

Over 1,000 simulated cases across all four playbooks, against a rule-based
baseline deciding the same customers: **₹64,47,527 gross recovered, ₹37,13,501
incremental** — 57.6% of gross, the rest being money that would have arrived
without the agent. A 37.2% settled recovery rate, 36% against the baseline's 20%
in the final window, and **zero** compliance violations — reported beside the 110
sends the guardrail blocked, because a zero with no denominator is not a claim
anyone should accept. Opt-outs are honoured in 6.2 seconds on average, and the
whole thing costs ₹0.06 per ₹100 recovered.

Those cases are synthetic. The machinery is not: webhooks are HMAC-verified,
payment links are genuine `rzp.io` URLs, and a customer paying one closes its
case and moves the bandit's posterior.
