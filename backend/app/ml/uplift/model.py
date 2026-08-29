"""A T-learner over the holdout group.

Two independent models: one fitted on cases the agent worked, one on the
controls it deliberately left alone. The difference between what they predict
for the same customer is that customer's estimated treatment effect — the CATE.
Positive means contact helped; negative means contact hurt.

That difference is the only defensible answer to "what did the agent earn?".
Gross recovery counts every rupee that arrived after a message, including from
customers who were going to pay regardless. The control group is what separates
the two, which is why the holdout path is guarded as carefully as it is.

**Snapshots store coefficients, not estimators.** A fitted model is persisted as
plain numbers in JSONB — weights, intercepts, and the feature names they line up
with. Pickling the sklearn object instead would tie every future read to the
exact library version that wrote it, and unpickling bytes out of a database is
arbitrary code execution wearing a hat. As a result prediction is a dot product,
and the agent loop never imports sklearn at all: only training does.

**Feature names travel with the snapshot.** ``bank`` is open-vocabulary — it is
the first four characters of whatever the payload said — so the set of columns
depends on what has been seen. Reconstructing the layout at predict time would
shift every column the first time a new bank appeared. Reading the stored names
instead means an unseen category encodes as all-zeros, which is the honest
representation of "no evidence about this" rather than a silent misalignment.
"""

from datetime import UTC, datetime
from typing import Any, cast

import numpy as np
from sklearn.linear_model import LogisticRegression

from app.agent.models import UpliftBucket
from app.logging import get_logger

logger = get_logger(__name__)

MODEL_TYPE = "t_learner"

#: Below this, a group's estimate is noise dressed as a number. Ten is not a
#: statistically respectable threshold — it is the point below which the model
#: should refuse to speak at all, and the ROI page says so rather than
#: rendering a confident figure from four observations.
MIN_GROUP_SAMPLES = 10

#: Categorical context fields, one-hot encoded. `hour_ist` is deliberately
#: excluded in favour of `period`: twenty-four columns of hour would swamp a
#: demo-scale sample, and period is the grouping the bandit already learns on.
_CATEGORICAL_FIELDS = (
    "bank",
    "method",
    "period",
    "ltv_bucket",
    "tenure_bucket",
    "amount_bucket",
)

#: Booleans pass through as a single 0/1 column each.
_BOOLEAN_FIELDS = ("has_salary_mismatch_pattern",)

#: CATE thresholds. Ordered high to low; the first match wins.
_BUCKET_THRESHOLDS: tuple[tuple[float, UpliftBucket], ...] = (
    (0.15, UpliftBucket.PERSUADABLE),
    (0.0, UpliftBucket.SURE_THING),
    (-0.1, UpliftBucket.LOST_CAUSE),
)


def bucket_for_cate(cate: float) -> UpliftBucket:
    """Map a treatment effect onto the four segments.

    The boundaries are what the product means by each word:

    * above 0.15 — contact moves the outcome enough to be worth its cost.
    * 0 to 0.15 — contact helps marginally; the customer was largely going to
      pay anyway, so the agent should not take credit for the recovery.
    * -0.1 to 0 — contact does nothing measurable. Sending is waste, not harm.
    * below -0.1 — contact makes things worse. This is the segment that
      justifies the whole exercise: without a control group there is no way to
      even observe it, and the agent would keep pushing customers away while
      reporting the ones who stayed as wins.
    """
    for threshold, bucket in _BUCKET_THRESHOLDS:
        if cate > threshold:
            return bucket
    return UpliftBucket.DO_NOT_DISTURB


def _column_names(contexts: list[dict[str, Any]]) -> list[str]:
    """The one-hot layout implied by a set of context vectors, sorted.

    Sorted so the same inputs always produce the same column order — an
    insertion-ordered layout would depend on which case happened to be read
    first, and a snapshot's coefficients would then be meaningless the next time
    the same data trained in a different order.
    """
    names: set[str] = set()
    for context in contexts:
        for field in _CATEGORICAL_FIELDS:
            value = context.get(field)
            names.add(f"{field}={value if value is not None else 'unknown'}")
    names.update(_BOOLEAN_FIELDS)
    return sorted(names)


def build_feature_matrix(
    contexts: list[dict[str, Any]],
    feature_names: list[str] | None = None,
) -> tuple[np.ndarray, list[str]]:
    """Encode context vectors as a dense matrix.

    Pass ``feature_names`` to encode against an existing layout — that is what
    prediction does, so a live case lands in the same columns the model was
    fitted on. A value not present in the layout contributes nothing rather than
    creating a column, which is what keeps an unseen bank from shifting every
    other feature one place to the right.
    """
    names = feature_names if feature_names is not None else _column_names(contexts)
    index = {name: position for position, name in enumerate(names)}
    matrix = np.zeros((len(contexts), len(names)), dtype=float)

    for row, context in enumerate(contexts):
        for field in _CATEGORICAL_FIELDS:
            value = context.get(field)
            key = f"{field}={value if value is not None else 'unknown'}"
            position = index.get(key)
            if position is not None:
                matrix[row, position] = 1.0
        for field in _BOOLEAN_FIELDS:
            position = index.get(field)
            if position is not None and context.get(field):
                matrix[row, position] = 1.0

    return matrix, names


def _fit(features: np.ndarray, labels: np.ndarray) -> tuple[list[float], float]:
    """Fit one arm of the T-learner, returning plain coefficients.

    A group whose outcomes are all identical — every control recovered, or none
    did — cannot be fitted: `LogisticRegression` requires two classes. That is a
    real state at small samples, not an error, so it degrades to a constant
    model at the observed rate, clipped away from 0 and 1 so the log-odds stay
    finite.
    """
    unique = np.unique(labels)
    if unique.size < 2:
        rate = float(np.clip(labels.mean() if labels.size else 0.5, 0.01, 0.99))
        intercept = float(np.log(rate / (1.0 - rate)))
        return [0.0] * features.shape[1], intercept

    model = LogisticRegression(max_iter=1000, C=1.0)
    model.fit(features, labels)
    return [float(w) for w in model.coef_[0]], float(model.intercept_[0])


def _probability(features: np.ndarray, coefficients: list[float], intercept: float) -> np.ndarray:
    """Logistic response for stored coefficients."""
    logits = features @ np.asarray(coefficients, dtype=float) + intercept
    return cast(np.ndarray, 1.0 / (1.0 + np.exp(-logits)))


def _rows(result: Any) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], getattr(result, "data", None) or [])


def _treated_samples(
    supabase_client: Any, merchant_id: str, playbook: str
) -> list[tuple[dict[str, Any], int]]:
    """Closed, non-holdout cases and whether they recovered.

    The features come from ``agent_decisions.bandit_context_vector``, not from
    the case row: ``recovery_cases`` never stored a context vector, and the
    decide step already writes the exact vector the arm was chosen under. Using
    it means treated and control features are built the same way — recomputing
    here would compare a vector made now against one frozen months ago.
    """
    cases = _rows(
        supabase_client.table("recovery_cases")
        .select("id, status, is_holdout, closed_at")
        .eq("merchant_id", merchant_id)
        .eq("playbook", playbook)
        # Batch-simulated cases carry no real outcome and would train the uplift
        # model on invented ones — a model fitted on a simulation, then used to
        # decide whether to contact actual customers.
        .is_("metadata->>is_batch_synthetic", "null")
        .execute()
    )
    eligible = {
        str(case["id"]): 1 if str(case.get("status")) == "recovered" else 0
        for case in cases
        if case.get("closed_at") and not case.get("is_holdout")
    }
    if not eligible:
        return []

    decisions = _rows(
        supabase_client.table("agent_decisions")
        .select("case_id, bandit_context_vector")
        .eq("merchant_id", merchant_id)
        .execute()
    )

    samples: list[tuple[dict[str, Any], int]] = []
    seen: set[str] = set()
    for decision in decisions:
        case_id = str(decision.get("case_id"))
        if case_id in seen or case_id not in eligible:
            continue
        context = decision.get("bandit_context_vector")
        if not isinstance(context, dict) or not context:
            continue
        seen.add(case_id)
        samples.append((context, eligible[case_id]))
    return samples


def _control_samples(
    supabase_client: Any, merchant_id: str, playbook: str
) -> list[tuple[dict[str, Any], int]]:
    """Resolved holdouts for this playbook, with their frozen context."""
    holdouts = _rows(
        supabase_client.table("uplift_holdouts")
        .select("case_id, outcome, context_features")
        .eq("merchant_id", merchant_id)
        .execute()
    )
    resolved = {
        str(row["case_id"]): row
        for row in holdouts
        if row.get("outcome") in {"recovered", "not_recovered"}
        and isinstance(row.get("context_features"), dict)
        and row["context_features"]
    }
    if not resolved:
        return []

    # The holdout row carries no playbook, so the case row decides which model
    # a control belongs to. A control trained into the wrong playbook's model
    # would be measuring a different agent.
    cases = _rows(
        supabase_client.table("recovery_cases")
        .select("id, playbook")
        .eq("merchant_id", merchant_id)
        .eq("playbook", playbook)
        .execute()
    )
    in_playbook = {str(case["id"]) for case in cases}

    return [
        (row["context_features"], 1 if row["outcome"] == "recovered" else 0)
        for case_id, row in resolved.items()
        if case_id in in_playbook
    ]


def train_uplift_model(
    supabase_client: Any,
    merchant_id: str,
    playbook: str,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Fit both arms and, by default, store the snapshot.

    Returns ``{"status": "insufficient_data", ...}`` rather than raising when
    either group is too small. A merchant on their first week has no controls
    yet, and that is the normal state, not a failure — the uplift check reads
    the absence of a snapshot and proceeds.
    """
    treated = _treated_samples(supabase_client, merchant_id, playbook)
    control = _control_samples(supabase_client, merchant_id, playbook)

    if len(treated) < MIN_GROUP_SAMPLES or len(control) < MIN_GROUP_SAMPLES:
        logger.info(
            "uplift_training_skipped",
            playbook=playbook,
            treated=len(treated),
            control=len(control),
            min_samples=MIN_GROUP_SAMPLES,
        )
        return {
            "status": "insufficient_data",
            "min_samples": MIN_GROUP_SAMPLES,
            "treated_samples": len(treated),
            "control_samples": len(control),
            "playbook": playbook,
        }

    contexts = [context for context, _ in treated] + [context for context, _ in control]
    _, feature_names = build_feature_matrix(contexts)

    treated_x, _ = build_feature_matrix([c for c, _ in treated], feature_names)
    treated_y = np.array([label for _, label in treated], dtype=int)
    control_x, _ = build_feature_matrix([c for c, _ in control], feature_names)
    control_y = np.array([label for _, label in control], dtype=int)

    treated_coef, treated_intercept = _fit(treated_x, treated_y)
    control_coef, control_intercept = _fit(control_x, control_y)

    # CATE across the whole observed population, used only to summarise the
    # segments — the per-case bucket is computed at predict time.
    all_x, _ = build_feature_matrix(contexts, feature_names)
    cate = _probability(all_x, treated_coef, treated_intercept) - _probability(
        all_x, control_coef, control_intercept
    )

    bucket_uplifts: dict[str, dict[str, Any]] = {}
    for bucket in UpliftBucket:
        if bucket is UpliftBucket.UNKNOWN:
            continue
        members = [float(value) for value in cate if bucket_for_cate(float(value)) is bucket]
        bucket_uplifts[bucket.value] = {
            "case_count": len(members),
            "mean_cate": round(sum(members) / len(members), 4) if members else 0.0,
        }

    snapshot: dict[str, Any] = {
        "status": "trained",
        "model_type": MODEL_TYPE,
        "feature_names": feature_names,
        "treated": {"coef": treated_coef, "intercept": treated_intercept},
        "control": {"coef": control_coef, "intercept": control_intercept},
        "treated_samples": len(treated),
        "control_samples": len(control),
        "treated_recovery_rate": round(float(treated_y.mean()), 4),
        "control_recovery_rate": round(float(control_y.mean()), 4),
        "mean_cate": round(float(cate.mean()), 4),
        "bucket_uplifts": bucket_uplifts,
    }

    # Coefficient magnitude, not a permutation importance: the models are
    # linear over one-hot columns, so |weight| is directly the feature's pull
    # on the log-odds and needs no extra fitting to read.
    snapshot["feature_importances"] = {
        name: round(abs(treated_coef[position] - control_coef[position]), 4)
        for position, name in enumerate(feature_names)
    }

    if persist:
        _store_snapshot(supabase_client, merchant_id, playbook, snapshot)

    logger.info(
        "uplift_model_trained",
        playbook=playbook,
        treated=len(treated),
        control=len(control),
        mean_cate=snapshot["mean_cate"],
    )
    return snapshot


def _store_snapshot(
    supabase_client: Any, merchant_id: str, playbook: str, snapshot: dict[str, Any]
) -> None:
    """Write the snapshot row, tolerating a write failure.

    A snapshot that fails to store costs the next prediction its model; raising
    would cost the caller its request, and the training data is still there to
    fit again.
    """
    try:
        supabase_client.table("uplift_model_snapshots").insert(
            {
                "merchant_id": merchant_id,
                "playbook": playbook,
                "trained_at": datetime.now(UTC).isoformat(),
                "model_type": MODEL_TYPE,
                "feature_importances": snapshot["feature_importances"],
                # The fitted parameters ride in bucket_uplifts alongside the
                # segment summary: it is the snapshot's only free-form JSONB
                # column, and splitting the model across a second table would
                # let a prediction read weights that never matched the
                # summary they were stored with.
                "bucket_uplifts": {
                    "buckets": snapshot["bucket_uplifts"],
                    "feature_names": snapshot["feature_names"],
                    "treated": snapshot["treated"],
                    "control": snapshot["control"],
                    "treated_recovery_rate": snapshot["treated_recovery_rate"],
                    "control_recovery_rate": snapshot["control_recovery_rate"],
                    "mean_cate": snapshot["mean_cate"],
                },
                "training_sample_size": snapshot["treated_samples"] + snapshot["control_samples"],
            }
        ).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("uplift_snapshot_store_error", playbook=playbook, error=str(exc))


def predict_uplift_bucket(
    context_features: dict[str, Any],
    model_snapshot: dict[str, Any] | None,
) -> tuple[UpliftBucket, float]:
    """Bucket and CATE for one case.

    Returns ``UNKNOWN`` with a zero effect when there is no usable snapshot.
    An untrained merchant must not be told its customers are do-not-disturb —
    the uplift check treats ``UNKNOWN`` as proceed, so the failure mode is
    acting without evidence rather than silently going quiet.
    """
    if not model_snapshot:
        return UpliftBucket.UNKNOWN, 0.0

    payload = model_snapshot.get("bucket_uplifts") or model_snapshot
    feature_names = payload.get("feature_names")
    treated = payload.get("treated") or {}
    control = payload.get("control") or {}
    if not feature_names or "coef" not in treated or "coef" not in control:
        return UpliftBucket.UNKNOWN, 0.0

    try:
        features, _ = build_feature_matrix([context_features], list(feature_names))
        treated_p = _probability(features, treated["coef"], float(treated["intercept"]))[0]
        control_p = _probability(features, control["coef"], float(control["intercept"]))[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("uplift_predict_error", error=str(exc))
        return UpliftBucket.UNKNOWN, 0.0

    cate = float(treated_p - control_p)
    return bucket_for_cate(cate), round(cate, 4)


def latest_snapshot(supabase_client: Any, merchant_id: str, playbook: str) -> dict[str, Any] | None:
    """The most recently trained snapshot for this merchant and playbook."""
    try:
        result = (
            supabase_client.table("uplift_model_snapshots")
            .select("*")
            .eq("merchant_id", merchant_id)
            .eq("playbook", playbook)
            .order("trained_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("uplift_snapshot_fetch_error", playbook=playbook, error=str(exc))
        return None

    rows = _rows(result)
    return rows[0] if rows else None
