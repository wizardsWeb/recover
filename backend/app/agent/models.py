"""Shared types for the nine-step agent loop.

Every step takes a case and returns one of these. That is the whole contract:
``core.py`` never reaches inside a step, and a step never writes a table another
step owns. When Phase 5 swaps the stub diagnose for a Gemini call, the only
thing that has to stay true is that it still returns a ``DiagnosisResult``.

Two conventions run through the file:

* **``is_stub`` is a field, not a comment.** A stubbed result is a real result
  that happens to be fabricated, and the audit trail has to be able to say so.
  Phase 5/6/9 flip these to ``False`` as each model lands, and the UI can show
  "reasoned" vs "placeholder" without guessing from the phase number.
* **String enums mirror the schema's comments.** ``recovery_cases.status`` is a
  plain ``TEXT`` column documented with a ``|``-separated list; these enums are
  that list, so a typo fails in Python instead of silently writing a status no
  query filters on.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Playbook(StrEnum):
    """The four recovery playbooks. Matches ``recovery_cases.playbook``."""

    FAILED_PAYMENT = "failed_payment"
    CHECKOUT_ABANDONMENT = "checkout_abandonment"
    SUBSCRIPTION_FAILURE = "subscription_failure"
    B2B_OVERDUE = "b2b_overdue"


class CaseStatus(StrEnum):
    """Lifecycle of a ``recovery_cases`` row."""

    OPEN = "open"
    IN_FLIGHT = "in_flight"
    RECOVERED = "recovered"
    STOPPED = "stopped"
    FAILED = "failed"
    HOLDOUT = "holdout"


class ActionType(StrEnum):
    """Everything the agent can physically do. Matches ``bandit_arms.action_type``."""

    RETRY_CHARGE = "retry_charge"
    SEND_PAYMENT_LINK = "send_payment_link"
    SEND_WHATSAPP = "send_whatsapp"
    SEND_SMS = "send_sms"
    SEND_EMAIL = "send_email"
    MANDATE_REREGISTER = "mandate_reregister"
    HUMAN_HANDOFF = "human_handoff"
    NO_OP = "no_op"


class DecisionSource(StrEnum):
    """Who chose the action — recorded so a bandit choice is never mistaken for a rule."""

    BANDIT = "bandit"
    LLM = "llm"
    RULE = "rule"
    HUMAN = "human"
    SYSTEM = "system"


class StepName(StrEnum):
    """The nine steps, in loop order."""

    DETECT = "detect"
    DIAGNOSE = "diagnose"
    UPLIFT_CHECK = "uplift_check"
    DECIDE = "decide"
    GUARDRAIL = "guardrail"
    EXECUTE = "execute"
    LISTEN = "listen"
    LEARN = "learn"
    AUDIT = "audit"


class GuardrailCheckResult(BaseModel):
    """One compliance check. Every check that runs is recorded, passing or not."""

    model_config = ConfigDict(populate_by_name=True)

    check_name: str
    passed: bool
    reason: str | None = None


class GuardrailResult(BaseModel):
    """The verdict plus the full check list that produced it.

    The check list is kept even on a ``BLOCK`` because "we stopped at check 2"
    is the auditable fact — a regulator asking why a message was not sent wants
    the checks that ran, not just the one that failed.
    """

    model_config = ConfigDict(populate_by_name=True)

    verdict: Literal["PASS", "BLOCK", "DOWNGRADE"]
    checks: list[GuardrailCheckResult]
    blocking_check: str | None = None
    downgrade_to: str | None = None  # arm name to fall back to


class DiagnosisResult(BaseModel):
    """Why the money is at risk, and how confident we are."""

    model_config = ConfigDict(populate_by_name=True)

    root_cause: str
    posterior_probability: float
    causal_path: list[str]
    supporting_evidence: list[str]
    alternative_hypotheses: list[dict[str, Any]]
    risk_factors: list[str]
    inferred_salary_date: str | None = None
    is_stub: bool = True  # False once Phase 5 LLM is wired


class UpliftBucket(StrEnum):
    """Causal segment. Matches ``recovery_cases.uplift_bucket``."""

    PERSUADABLE = "persuadable"
    SURE_THING = "sure_thing"
    LOST_CAUSE = "lost_cause"
    DO_NOT_DISTURB = "dnd"
    UNKNOWN = "unknown"


class UpliftVerdict(BaseModel):
    """Whether contacting this customer changes the outcome at all."""

    model_config = ConfigDict(populate_by_name=True)

    bucket: UpliftBucket
    estimated_lift: float
    verdict: Literal["PROCEED", "SKIP"]
    reasoning: str
    is_stub: bool = True


class BanditAlternative(BaseModel):
    """An arm that was on the table, and why it lost.

    Recorded for every arm, not just the winner: the counterfactual is what
    makes the decision explainable after the fact.
    """

    model_config = ConfigDict(populate_by_name=True)

    arm_name: str
    expected_reward: float
    chosen: bool
    not_chosen_reason: str | None = None


class DecisionResult(BaseModel):
    """The chosen action, with its provenance."""

    model_config = ConfigDict(populate_by_name=True)

    chosen_arm: str
    action_type: ActionType
    action_params: dict[str, Any]
    decision_source: DecisionSource
    bandit_mode: Literal["exploit", "explore"] | None = None
    arm_confidence: float | None = None
    expected_recovery_probability: float | None = None
    alternatives_considered: list[BanditAlternative] = Field(default_factory=list)
    reasoning: str
    message_tone: str | None = None
    is_stub: bool = True


class ExecutionStatus(StrEnum):
    """Outcome of one execution attempt."""

    SUCCESS = "success"
    FAILURE = "failure"
    SIMULATED = "simulated"
    SKIPPED = "skipped"


class ExecutionResult(BaseModel):
    """What was sent where, and what came back."""

    model_config = ConfigDict(populate_by_name=True)

    action_type: ActionType
    adapter: str
    status: ExecutionStatus
    idempotency_key: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    simulated: bool = True  # False once real adapters wired (future phase)


class ReplyIntent(StrEnum):
    """What an inbound customer message means."""

    EXPLICIT_OPT_OUT = "explicit_opt_out"
    PROMISE_TO_PAY = "promise_to_pay"
    CHURN_CONFIRMATION = "churn_confirmation"
    HARDSHIP_SIGNAL = "hardship_signal"
    SOFT_PROMISE = "soft_promise"
    # "the app charged me twice", "goods came damaged" — a recovery message is
    # the wrong answer to a complaint, so the classifier gets a name for it.
    PRODUCT_ISSUE = "product_issue"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class ListenResult(BaseModel):
    """Classification of one customer reply.

    The three boolean signals are deliberately separate from ``intent``: they
    are the ones that change what the agent is *allowed* to do next, and code
    that enforces consent should not have to know the full intent taxonomy.
    """

    model_config = ConfigDict(populate_by_name=True)

    reply_id: str | None = None
    intent: ReplyIntent
    language: str
    opt_out_signal: bool
    hardship_signal: bool
    churn_signal: bool
    extracted_entities: dict[str, Any] = Field(default_factory=dict)
    recommended_state_update: str | None = None
    # Both are LLM-only. The pattern matcher cannot read tone, and it has no
    # calibrated notion of confidence — leaving them None is the honest answer
    # rather than inventing a 1.0 for a keyword hit.
    sentiment: str | None = None
    confidence: float | None = None
    is_stub: bool = True  # False when the Gemini classifier answered


class AgentLoopResult(BaseModel):
    """One full pass of the loop, step results included.

    ``steps_completed`` is the honest record of how far the pass got: a case
    blocked at the guardrail has four entries, not nine, and the absent step
    results are ``None`` rather than empty objects.
    """

    model_config = ConfigDict(populate_by_name=True)

    case_id: str
    trace_id: str
    playbook: Playbook
    steps_completed: list[StepName]
    final_status: CaseStatus
    diagnosis: DiagnosisResult | None = None
    uplift: UpliftVerdict | None = None
    decision: DecisionResult | None = None
    guardrail: GuardrailResult | None = None
    execution: ExecutionResult | None = None
    listen: ListenResult | None = None
    error: str | None = None
