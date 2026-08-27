"""Step 3 — Uplift check: would contacting this customer change anything?

Four buckets matter. *Persuadable* customers pay because you asked;
*sure things* would have paid anyway and the message only costs goodwill;
*lost causes* will not pay whatever you send; and *do-not-disturb* customers
are actively made worse by contact — the message is what makes them churn.

Only the first bucket is worth a message. Answering that question needs a
T-learner trained against a real holdout group, which is Phase 9. Until then
this returns ``PROCEED`` for everything, flagged ``is_stub=True`` so nobody
mistakes a pass-through for a causal estimate.
"""

from typing import Any

from app.agent.models import UpliftBucket, UpliftVerdict


async def run_uplift_check(case: dict[str, Any], diagnosis: dict[str, Any]) -> UpliftVerdict:
    """Always returns PROCEED with the 'persuadable' bucket.

    Phase 9 replaces this with a real T-learner uplift model using a holdout
    group for causal attribution.
    """
    return UpliftVerdict(
        bucket=UpliftBucket.PERSUADABLE,
        estimated_lift=0.50,
        verdict="PROCEED",
        reasoning=(
            "Stub uplift check — all cases proceed until Phase 9 implements real causal model."
        ),
        is_stub=True,
    )
