"""Step 3 — Uplift check: would contacting this customer change anything?

Four buckets matter. *Persuadable* customers pay because you asked;
*sure things* would have paid anyway and the message only costs goodwill;
*lost causes* will not pay whatever you send; and *do-not-disturb* customers
are actively made worse by contact — the message is what makes them churn.

The estimate comes from a T-learner fitted against the holdout group, read here
as a stored snapshot rather than a live model. Two consequences follow from that
and both are deliberate:

* **No model means proceed.** A merchant with no controls yet has no snapshot,
  and the honest response to "we cannot estimate this" is to act as the agent
  did before uplift existed — not to fall silent. Silence dressed as caution
  would look identical to a working product and recover nothing.
* **Only harm and futility stop a send.** ``sure_thing`` proceeds. The customer
  was largely going to pay regardless, so the message is close to free and the
  attribution — not the action — is what has to be honest. The ROI page is where
  that distinction is drawn, by not counting those recoveries as caused.

``dnd`` is the bucket that justifies the holdout group's cost. Without a control
there is no way to observe a segment that contact makes worse, and the agent
would go on pushing those customers away while reporting the ones who stayed.
"""

from typing import Any

from app.agent.models import UpliftBucket, UpliftVerdict
from app.logging import get_logger
from app.ml.uplift.model import latest_snapshot, predict_uplift_bucket

logger = get_logger(__name__)

#: Buckets where sending is not worth it. Everything else proceeds.
_SKIP_BUCKETS = frozenset({UpliftBucket.LOST_CAUSE, UpliftBucket.DO_NOT_DISTURB})

_REASONING: dict[UpliftBucket, str] = {
    UpliftBucket.PERSUADABLE: (
        "Contacting customers in this context recovers materially more often than leaving "
        "them alone, measured against the holdout group."
    ),
    UpliftBucket.SURE_THING: (
        "This customer is likely to pay with or without a message. Proceeding, but the "
        "recovery is not counted as caused by the agent."
    ),
    UpliftBucket.LOST_CAUSE: (
        "Treated and untreated customers in this context recover at the same low rate. "
        "A message changes nothing, so nothing is sent."
    ),
    UpliftBucket.DO_NOT_DISTURB: (
        "Customers in this context recover less often when contacted than when left alone. "
        "The message is what drives them away, so it is not sent."
    ),
    UpliftBucket.UNKNOWN: (
        "No uplift model for this playbook yet — not enough resolved holdout cases to "
        "estimate a treatment effect. Proceeding on the playbook's own judgement."
    ),
}


async def run_uplift_check(
    case: dict[str, Any],
    diagnosis: dict[str, Any],
    supabase_client: Any = None,
    context_features: dict[str, Any] | None = None,
    merchant_id: str | None = None,
    playbook: str | None = None,
) -> UpliftVerdict:
    """Estimate this case's treatment effect and decide whether to act.

    Everything after ``diagnosis`` is optional so the signature stays callable
    from tests and from any path that has not extracted a context vector. Absent
    them the check degrades to the pre-Phase-9 behaviour — proceed, flagged as a
    stub — rather than guessing at a bucket it has no features for.
    """
    if not supabase_client or not context_features or not merchant_id or not playbook:
        return UpliftVerdict(
            bucket=UpliftBucket.UNKNOWN,
            estimated_lift=0.0,
            verdict="PROCEED",
            reasoning=_REASONING[UpliftBucket.UNKNOWN],
            is_stub=True,
        )

    snapshot = latest_snapshot(supabase_client, merchant_id, playbook)
    bucket, estimated_lift = predict_uplift_bucket(context_features, snapshot)

    verdict: str = "SKIP" if bucket in _SKIP_BUCKETS else "PROCEED"
    logger.info(
        "uplift_check_complete",
        bucket=bucket.value,
        estimated_lift=estimated_lift,
        verdict=verdict,
        has_snapshot=snapshot is not None,
    )

    return UpliftVerdict(
        bucket=bucket,
        estimated_lift=estimated_lift,
        verdict="SKIP" if verdict == "SKIP" else "PROCEED",
        reasoning=_REASONING[bucket],
        # A prediction from a real snapshot is not a stub even when it says
        # UNKNOWN — but with no snapshot at all there was nothing to predict
        # from, and the UI's provenance badge should keep saying so.
        is_stub=snapshot is None,
    )
