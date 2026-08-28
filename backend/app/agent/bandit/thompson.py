"""Thompson Sampling over Beta posteriors, in the standard library.

Each arm in a (merchant, playbook, context bucket) carries a Beta(alpha, beta).
Choosing an arm means drawing one sample from every arm's posterior and playing
whichever drew highest. Observing the outcome moves that arm's alpha (recovered)
or beta (did not), and nothing else moves.

**Why sampling rather than picking the best mean.** An arm's mean is a point
estimate, and a policy that always plays the current best mean stops gathering
evidence about every other arm — including the one that is actually best but got
unlucky in its first three pulls. Drawing from the posterior makes exploration
proportional to uncertainty: a Beta(1,1) is flat and will often out-draw a
Beta(18,4), while a Beta(180,40) almost never loses to noise. The bandit
explores hardest exactly where it knows least, and stops on its own as evidence
accumulates. No epsilon to tune, no schedule to decay.

**Why no numpy.** ``random.betavariate`` is in the standard library and this is
one draw per arm per case — a few dozen per decision. Adding numpy to a
container image for that is a dependency with no payoff.

The ``explore``/``exploit`` label is descriptive, not a mode the caller sets.
Every decision is one draw; the label reports whether that draw happened to pick
an arm whose *mean* sits below the runner-up's, which is the honest reading of
"this pull bought information rather than return".
"""

import random
from datetime import UTC, datetime
from typing import Any, NamedTuple

from app.logging import get_logger

logger = get_logger(__name__)

#: Uniform prior. Beta(1,1) is flat on [0,1]: before any evidence, every win
#: rate is equally plausible. Starting anywhere else asserts a belief the system
#: has not earned.
PRIOR_ALPHA = 1.0
PRIOR_BETA = 1.0

#: Recent network readings to average for a warm start.
_NETWORK_PRIOR_ROWS = 20

#: Pseudo-observations a network-informed prior is worth. Ten is a deliberate
#: trade: enough to change the first few decisions in a context nobody has
#: played, and light enough that ten real pulls outweigh it. It is the number
#: that decides how long a *wrong* network reading steers an arm, so it is
#: stated here rather than buried in the arithmetic.
NETWORK_PRIOR_STRENGTH = 10.0

#: Below this, the network is saying the instrument is in trouble and arms that
#: route around it are worth a nudge. Above it, the network has nothing to say
#: about a WhatsApp message and does not pretend to.
NETWORK_DEGRADED_RATE = 0.60

#: How much better an avoiding arm is assumed to be while the instrument is
#: degraded. Small: this is "try something else", not "this will work".
NETWORK_AVOIDANCE_RATE = 0.62

#: alpha + beta at or below this means the arm carries prior only — no real
#: observation has moved it. Surfaced so the UI can say "untried" rather than
#: present a 50% expected win rate as a measurement.
COLD_START_MASS = 2.0

#: Reward above this counts as a success. Rewards are binary today; the
#: threshold exists so an amount-normalised reward can be fed in later without
#: changing the shape of the update rule.
SUCCESS_THRESHOLD = 0.5


class ArmSample(NamedTuple):
    """One arm's posterior, its draw, and what that draw means."""

    arm_name: str
    sampled_theta: float
    alpha: float
    beta: float
    n_pulls: int
    expected_win_rate: float
    is_cold: bool


def sample_beta(alpha: float, beta: float) -> float:
    """Draw from Beta(alpha, beta), or 0.5 if the parameters are unusable.

    ``random.betavariate`` requires both parameters strictly positive and raises
    otherwise. A corrupt row — a zero, a negative, a NaN written by some future
    bug — must not take down a decision, so it degrades to a coin flip: maximal
    uncertainty, which is the truthful answer for a posterior that cannot be
    read.
    """
    try:
        return random.betavariate(alpha, beta)  # noqa: S311 - not cryptographic
    except (ValueError, OverflowError, TypeError):
        logger.warning("bandit_invalid_posterior", alpha=alpha, beta=beta)
        return 0.5


def run_thompson_sampling(
    arms: list[str],
    posteriors: dict[str, tuple[float, float, int]],
) -> list[ArmSample]:
    """Draw once per arm and return every arm, best draw first.

    The full ranking comes back, not just the winner. A decision is only
    explainable against the options it beat, and the arms that lost — with their
    draws and their means — are what the case detail page renders.

    An arm absent from ``posteriors`` has never been pulled in this context and
    takes the flat prior, which is what keeps a new arm competitive on its first
    appearance instead of permanently invisible.
    """
    samples = []
    for arm in arms:
        alpha, beta, n_pulls = posteriors.get(arm, (PRIOR_ALPHA, PRIOR_BETA, 0))
        mass = alpha + beta
        samples.append(
            ArmSample(
                arm_name=arm,
                sampled_theta=sample_beta(alpha, beta),
                alpha=alpha,
                beta=beta,
                n_pulls=n_pulls,
                # The posterior mean. Undefined at zero mass, which a positive
                # prior makes impossible — guarded rather than assumed.
                expected_win_rate=(alpha / mass) if mass > 0 else 0.5,
                is_cold=mass <= COLD_START_MASS,
            )
        )

    return sorted(samples, key=lambda s: s.sampled_theta, reverse=True)


def is_exploring(chosen: ArmSample, runner_up: ArmSample | None) -> bool:
    """Whether this pull bought information rather than expected return.

    True when the arm that drew highest has a *lower* mean than the arm behind
    it — the draw overruled the standing evidence. With one arm on the table
    there is no counterfactual, so nothing was explored.
    """
    if runner_up is None:
        return False
    return chosen.expected_win_rate < runner_up.expected_win_rate


def warm_start_from_network(
    supabase_client: Any,
    arms: list[str],
    bank: str,
    method: str,
    hour_of_day: int,
) -> dict[str, tuple[float, float, int]]:
    """Borrow the network's view of an instrument as a starting belief.

    A merchant's first case in a context has no history, and a flat prior makes
    the bandit try a retry into a bank the network already knows is failing —
    spending one of a small number of RBI-permitted attempts to learn something
    every other merchant found out an hour ago. This is where that knowledge
    crosses over.

    **The translation is deliberately loose, and the strength reflects that.**
    The network measures whether a *retry settles*; the bandit's reward is
    whether a *case recovers*. They are correlated, not equal — a customer can
    pay through another route entirely. So the network rate seeds retry arms
    only, and the other arms are left alone unless the instrument is actually
    degraded, at which point "route around it" earns a modest nudge. Speaking
    only where there is evidence is the whole difference between a prior and a
    guess.

    ``n_pulls`` is zero on every entry, and nothing here is written to
    ``bandit_posteriors``. A prior is not an observation: persisting it would
    make a borrowed belief indistinguishable from a learned one on the very
    dashboard that exists to show what the bandit has learned.
    """
    from app.agent.playbooks import ARM_TO_ACTION_TYPE

    try:
        rows = (
            supabase_client.table("network_stats")
            .select("success_rate, sample_size, window_end")
            .eq("bank", bank.upper())
            .eq("method", method.lower())
            .eq("hour_of_day", hour_of_day)
            .order("window_end", desc=True)
            .limit(_NETWORK_PRIOR_ROWS)
            .execute()
        ).data or []
    except Exception as exc:  # noqa: BLE001 - no network view is a valid state
        logger.warning("bandit_warm_start_error", bank=bank, error=str(exc))
        return {}

    weighted = 0.0
    total = 0.0
    for row in rows:
        try:
            size = float(row.get("sample_size") or 0)
            rate = float(row.get("success_rate") or 0.0)
        except (TypeError, ValueError):
            continue
        if size > 0:
            weighted += rate * size
            total += size

    if total <= 0:
        return {}

    network_rate = min(0.98, max(0.02, weighted / total))
    degraded = network_rate < NETWORK_DEGRADED_RATE

    priors: dict[str, tuple[float, float, int]] = {}
    for arm in arms:
        action = ARM_TO_ACTION_TYPE.get(arm)
        retries = action is not None and action.value == "retry_charge"
        if retries:
            rate = network_rate
        elif degraded:
            rate = NETWORK_AVOIDANCE_RATE
        else:
            # Nothing to say. A flat prior is the honest belief about a message
            # the network has no measurement of.
            continue
        priors[arm] = (
            rate * NETWORK_PRIOR_STRENGTH,
            (1.0 - rate) * NETWORK_PRIOR_STRENGTH,
            0,
        )

    if priors:
        logger.info(
            "bandit_warm_started_from_network",
            bank=bank,
            method=method,
            hour_of_day=hour_of_day,
            network_rate=round(network_rate, 3),
            degraded=degraded,
            arms=len(priors),
        )
    return priors


async def fetch_posteriors(
    supabase_client: Any,
    merchant_id: str,
    playbook: str,
    context_bucket: str,
    arms: list[str],
    context: dict[str, Any] | None = None,
) -> dict[str, tuple[float, float, int]]:
    """Load ``(alpha, beta, n_pulls)`` per arm for one context bucket.

    Returns ``{}`` on any failure. That is not swallowing an error — an empty
    map is exactly "no evidence": every arm falls back to the flat prior and the
    bandit behaves like a fresh one rather than refusing to decide. A recovery
    must not be lost because a statistics table was unreachable.

    Passing ``context`` opts this call into a network warm start when the bucket
    turns out to be completely unplayed. It is opt-in rather than automatic
    because ``update_posterior`` also calls this function: warm-starting there
    would fold the first real outcome into a borrowed prior and then *write the
    sum back*, which is how a guess becomes indistinguishable from evidence.
    Only the decide path passes it.
    """
    try:
        resp = (
            supabase_client.table("bandit_posteriors")
            .select("arm_name, alpha, beta, n_pulls")
            .eq("merchant_id", merchant_id)
            .eq("playbook", playbook)
            .eq("context_bucket", context_bucket)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 - no posteriors is a valid state
        logger.warning("bandit_posterior_fetch_error", error=str(exc), playbook=playbook)
        return {}

    wanted = set(arms)
    result: dict[str, tuple[float, float, int]] = {}
    for row in resp.data or []:
        name = str(row.get("arm_name"))
        # Arms retired from a playbook keep their rows; filtering here stops a
        # decommissioned arm being resurrected by its own history.
        if name not in wanted:
            continue
        try:
            result[name] = (
                float(row.get("alpha", PRIOR_ALPHA)),
                float(row.get("beta", PRIOR_BETA)),
                int(row.get("n_pulls", 0)),
            )
        except (TypeError, ValueError):
            logger.warning("bandit_posterior_unreadable", arm=name)

    # Strictly "nothing at all". A bucket with one played arm has real evidence
    # in it, and mixing a borrowed prior into the other seven would make the
    # bandit compare what it learned against what it assumed.
    if not result and context:
        bank = str(context.get("bank") or "")
        method = str(context.get("method") or "")
        hour = context.get("hour_ist")
        if bank and method and isinstance(hour, int):
            return warm_start_from_network(supabase_client, arms, bank, method, hour)

    return result


def write_posterior(
    supabase_client: Any,
    merchant_id: str,
    playbook: str,
    arm_name: str,
    context_bucket: str,
    *,
    alpha: float,
    beta: float,
    n_pulls: int,
) -> None:
    """Insert or update one posterior row, keyed on the table's UNIQUE tuple.

    Select-then-write rather than PostgREST's ``upsert``: the composite conflict
    target ``(merchant_id, playbook, arm_name, context_bucket)`` is awkward
    through the client, and every caller has to read the current alpha before it
    can compute the next one anyway — so reading first costs nothing.

    Plain ``def``: the Supabase Python client is synchronous, so there is
    nothing here to await, and marking it ``async`` would invite a caller to
    forget the ``await`` and silently write nothing.

    This is a read-modify-write and is **not atomic**. Two passes closing the
    same context in the same instant can lose one increment. Against a posterior
    with double-digit mass that is a rounding error; a production version wants
    a Postgres function doing ``alpha = alpha + $1`` in a single statement.
    """
    now = datetime.now(UTC).isoformat()
    existing = (
        supabase_client.table("bandit_posteriors")
        .select("id")
        .eq("merchant_id", merchant_id)
        .eq("playbook", playbook)
        .eq("arm_name", arm_name)
        .eq("context_bucket", context_bucket)
        .limit(1)
        .execute()
    )

    values = {"alpha": alpha, "beta": beta, "n_pulls": n_pulls, "last_updated_at": now}
    if existing.data:
        supabase_client.table("bandit_posteriors").update(values).eq(
            "id", existing.data[0]["id"]
        ).execute()
        return

    supabase_client.table("bandit_posteriors").insert(
        {
            "merchant_id": merchant_id,
            "playbook": playbook,
            "arm_name": arm_name,
            "context_bucket": context_bucket,
            **values,
        }
    ).execute()


async def update_posterior(
    supabase_client: Any,
    merchant_id: str,
    playbook: str,
    arm_name: str,
    context_bucket: str,
    reward: float,
) -> None:
    """Fold one observed outcome into an arm's posterior.

    Success adds 1 to alpha, failure adds 1 to beta, and ``n_pulls`` counts
    both. An arm with no row yet starts from the flat prior, so its first
    observation lands on Beta(2,1) or Beta(1,2) rather than on nothing.

    Never raises: reward posting runs after a case has already closed, and an
    exception here would fail a pass whose useful work is already done.
    """
    try:
        current = await fetch_posteriors(
            supabase_client, merchant_id, playbook, context_bucket, [arm_name]
        )
        alpha, beta, n_pulls = current.get(arm_name, (PRIOR_ALPHA, PRIOR_BETA, 0))

        if reward > SUCCESS_THRESHOLD:
            alpha += 1.0
        else:
            beta += 1.0

        write_posterior(
            supabase_client,
            merchant_id,
            playbook,
            arm_name,
            context_bucket,
            alpha=alpha,
            beta=beta,
            n_pulls=n_pulls + 1,
        )
        logger.info(
            "bandit_posterior_updated",
            arm=arm_name,
            bucket=context_bucket,
            alpha=alpha,
            beta=beta,
            reward=reward,
        )
    except Exception as exc:  # noqa: BLE001 - learning must not break the loop
        logger.warning("bandit_posterior_update_error", arm=arm_name, error=str(exc))
