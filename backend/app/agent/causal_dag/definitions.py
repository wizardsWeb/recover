"""The graphs themselves: what can cause what, and how strongly.

Four DAGs, one per playbook, each a bipartite graph from latent **root causes**
to the **observables** they produce. A root cause is the thing a merchant would
act on ("their salary lands after your mandate does"); an observable is
something a payload or a customer's history can settle without inference ("the
failure code was insufficient funds").

**Every number here was written by a person, not fitted.** They are the domain
claims this product is making, stated where they can be argued with. A prior
says how often each cause is the real one across Indian recovery cases of that
type; a likelihood says how often that cause produces that symptom. Getting one
wrong produces a confidently wrong diagnosis, which is why they are in a module
of their own rather than scattered through the inference code.

**Shape, and why it is enough.** No observable has two parents and there are no
v-structures, so exact inference over these graphs *is* Naive Bayes — a product
of likelihoods against a prior, normalised. A general-purpose engine would
compute the same posteriors from the same table. That is the entire reason
`pgmpy` is not a dependency: it would bring pandas, statsmodels and
huggingface-hub along to multiply eight numbers.

**Likelihoods are stored per cause, not as an edge list.** Naive Bayes needs
`P(observable | cause)` for *every* pair, including the pairs nobody thought
worth drawing an arrow for — and treating a missing pair as zero would make a
single unexpected symptom eliminate a cause outright. Each observable therefore
carries a `base_rate`, the chance it fires when something else is driving, and
an explicit likelihood is the exception that says "this cause makes this symptom
much more, or much less, likely than that". The edge list the API renders is
derived from the entries that differ materially from base.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Bumped when a prior, a likelihood or a node changes. Stored on every
#: diagnosis so a posterior can be traced to the table that produced it — the
#: same case reasoned about under v1 and v2 should not silently look like a
#: model that changed its mind.
DAG_VERSION = "v1"

#: How far a likelihood must sit from an observable's base rate before it counts
#: as an edge worth drawing. Everything is used in the arithmetic; this only
#: decides what the diagram shows, because a fully connected bipartite graph is
#: a picture of nothing.
EDGE_VISIBILITY_THRESHOLD = 0.15


@dataclass(frozen=True)
class CausalNode:
    """One node. Root causes carry a prior; observables carry a base rate."""

    node_id: str
    node_type: str  # "root_cause" | "observable"
    label: str
    #: Root causes only: how often this is the true cause, before evidence.
    prior_probability: float | None = None
    #: Observables only: `P(observable | some cause other than the one asked
    #: about)`. The fallback when a cause has no explicit likelihood for it.
    base_rate: float | None = None
    #: A sentence a merchant would recognise, for the diagram's tooltip.
    description: str = ""


@dataclass(frozen=True)
class CausalEdge:
    """A cause and the symptom it produces, with `P(symptom | cause)`."""

    from_node: str
    to_node: str
    likelihood: float


@dataclass(frozen=True)
class CausalDag:
    """One playbook's graph, plus the lookups inference and the API need."""

    playbook: str
    nodes: tuple[CausalNode, ...]
    #: `cause -> {observable: P(observable | cause)}`. Sparse: anything absent
    #: falls back to that observable's `base_rate`.
    likelihoods: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def root_causes(self) -> tuple[CausalNode, ...]:
        return tuple(node for node in self.nodes if node.node_type == "root_cause")

    @property
    def observables(self) -> tuple[CausalNode, ...]:
        return tuple(node for node in self.nodes if node.node_type == "observable")

    def node(self, node_id: str) -> CausalNode | None:
        return next((node for node in self.nodes if node.node_id == node_id), None)

    def likelihood(self, cause: str, observable: str) -> float:
        """`P(observable | cause)`, falling back to the observable's base rate."""
        explicit = self.likelihoods.get(cause, {}).get(observable)
        if explicit is not None:
            return explicit
        node = self.node(observable)
        return node.base_rate if node and node.base_rate is not None else 0.5

    @property
    def edges(self) -> tuple[CausalEdge, ...]:
        """The arrows worth drawing: likelihoods far enough from base to matter.

        A merchant looking at this diagram wants to see what explains their
        case. Rendering all fifty-odd pairs would be a complete bipartite graph,
        which communicates nothing at all.
        """
        drawn: list[CausalEdge] = []
        for cause in self.root_causes:
            for observable in self.observables:
                value = self.likelihood(cause.node_id, observable.node_id)
                base = observable.base_rate if observable.base_rate is not None else 0.5
                if value - base >= EDGE_VISIBILITY_THRESHOLD:
                    drawn.append(CausalEdge(cause.node_id, observable.node_id, round(value, 3)))
        return tuple(drawn)


def _observable(node_id: str, label: str, base_rate: float, description: str = "") -> CausalNode:
    return CausalNode(node_id, "observable", label, base_rate=base_rate, description=description)


def _cause(node_id: str, label: str, prior: float, description: str = "") -> CausalNode:
    return CausalNode(
        node_id, "root_cause", label, prior_probability=prior, description=description
    )


# ── Subscription failure ───────────────────────────────────────────────
# The S1 graph, and the one the product's headline claim rests on: that a
# recurring failure on the 1st with an insufficient-funds code is a *timing*
# problem, not a broken instrument, and the fix is to retry when the salary
# lands rather than to keep hitting an empty account.

SUBSCRIPTION_FAILURE = CausalDag(
    playbook="subscription_failure",
    nodes=(
        _observable("payment_failed", "Payment failed", 0.99, "The mandate presentment failed."),
        _observable(
            "insufficient_funds_code",
            "Insufficient funds code",
            0.10,
            "The issuer returned an insufficient-balance decline.",
        ),
        _observable(
            "failure_on_1st_dom",
            "Failed on the 1st",
            0.15,
            "The attempt landed on the first of the month.",
        ),
        _observable(
            "failure_on_1st_for_3_months",
            "Failed on the 1st, three months running",
            0.05,
            "The same day-of-month has failed repeatedly — a pattern, not a bad month.",
        ),
        _observable(
            "manual_recovery_on_day_4_to_8",
            "Paid manually between the 4th and 8th",
            0.10,
            "They do pay — a few days later, once money has arrived.",
        ),
        _observable(
            "mandate_revoked_code",
            "Mandate revoked code",
            0.03,
            "The bank says the standing instruction no longer exists.",
        ),
        _observable("card_expired_code", "Card expired code", 0.03, "The instrument has expired."),
        _observable(
            "bank_downtime_signal",
            "Bank degraded on the network",
            0.04,
            "Cross-merchant statistics show this rail failing right now.",
        ),
        _cause(
            "salary_cycle_mismatch_with_competing_emi",
            "Salary cycle mismatch",
            0.35,
            "Their pay lands after your mandate presents, and other EMIs get there first.",
        ),
        _cause(
            "mandate_revoked_by_customer",
            "Mandate revoked",
            0.15,
            "They cancelled the standing instruction at their bank.",
        ),
        _cause("account_closed", "Account closed", 0.05, "The funding account no longer exists."),
        _cause("card_expired", "Card expired", 0.10, "The card on file needs replacing."),
        _cause(
            "bank_transient_failure",
            "Bank transient failure",
            0.20,
            "The rail is having a bad hour; nothing is wrong with the customer.",
        ),
        _cause(
            "insufficient_credit_limit",
            "Credit limit exhausted",
            0.08,
            "The card is live but has no headroom left.",
        ),
        _cause(
            "unknown",
            "Unexplained",
            0.07,
            "Nothing on file distinguishes a cause. Deliberately present — a graph "
            "with no catch-all forces every case into a story it may not have.",
        ),
    ),
    likelihoods={
        "salary_cycle_mismatch_with_competing_emi": {
            "insufficient_funds_code": 0.90,
            "failure_on_1st_dom": 0.85,
            "failure_on_1st_for_3_months": 0.55,
            "manual_recovery_on_day_4_to_8": 0.75,
            "mandate_revoked_code": 0.01,
            "card_expired_code": 0.01,
        },
        "mandate_revoked_by_customer": {
            "mandate_revoked_code": 0.95,
            "insufficient_funds_code": 0.02,
            "manual_recovery_on_day_4_to_8": 0.05,
            "card_expired_code": 0.01,
            "failure_on_1st_for_3_months": 0.02,
        },
        "account_closed": {
            "mandate_revoked_code": 0.30,
            "insufficient_funds_code": 0.15,
            "manual_recovery_on_day_4_to_8": 0.02,
            "card_expired_code": 0.02,
            "failure_on_1st_for_3_months": 0.02,
        },
        "card_expired": {
            "card_expired_code": 0.92,
            "insufficient_funds_code": 0.02,
            "mandate_revoked_code": 0.02,
            "manual_recovery_on_day_4_to_8": 0.10,
        },
        "bank_transient_failure": {
            "bank_downtime_signal": 0.80,
            "insufficient_funds_code": 0.05,
            "manual_recovery_on_day_4_to_8": 0.25,
            "failure_on_1st_dom": 0.12,
            "mandate_revoked_code": 0.01,
            "card_expired_code": 0.02,
        },
        "insufficient_credit_limit": {
            "insufficient_funds_code": 0.85,
            "manual_recovery_on_day_4_to_8": 0.45,
            "failure_on_1st_for_3_months": 0.25,
            "failure_on_1st_dom": 0.20,
            "mandate_revoked_code": 0.01,
            "card_expired_code": 0.02,
        },
        # `unknown` deliberately carries no overrides: it explains every symptom
        # exactly as well as the background does, which is what makes it win
        # when the evidence fits nothing in particular.
    },
)


# ── Checkout abandonment ───────────────────────────────────────────────
# Where in the flow they left is the evidence. Someone who reached OTP and
# stopped had already decided to pay; someone who never chose a method had not.

CHECKOUT_ABANDONMENT = CausalDag(
    playbook="checkout_abandonment",
    nodes=(
        _observable(
            "dropped_at_method_select",
            "Left at method selection",
            0.20,
            "They never chose how to pay.",
        ),
        _observable(
            "dropped_at_otp", "Left at OTP", 0.15, "They got as far as the one-time password."
        ),
        _observable(
            "dropped_at_3ds", "Left at 3-D Secure", 0.10, "The bank's own step is where they went."
        ),
        _observable(
            "high_session_duration",
            "Long session before leaving",
            0.25,
            "Minutes on the page, not seconds — deliberation rather than a misclick.",
        ),
        _observable(
            "returning_customer", "Returning customer", 0.35, "They have bought here before."
        ),
        _observable("cart_value_above_1000", "Cart over ₹1,000", 0.40, "Enough to think about."),
        _observable(
            "first_time_abandonment",
            "First time they have abandoned",
            0.45,
            "No history of leaving carts behind.",
        ),
        _cause(
            "price_sensitivity_at_checkout",
            "Price sensitivity",
            0.40,
            "The total, with shipping and tax, was more than they had in mind.",
        ),
        _cause(
            "distracted_multitasking",
            "Distracted",
            0.20,
            "Nothing was wrong; something else happened.",
        ),
        _cause(
            "trust_issue_at_checkout",
            "Trust hesitation",
            0.10,
            "They reached the bank's page and thought better of it.",
        ),
        _cause(
            "payment_method_unavailable",
            "Preferred method missing",
            0.15,
            "What they wanted to pay with was not on offer.",
        ),
        _cause(
            "technical_failure_unlogged",
            "Silent technical failure",
            0.10,
            "Something broke and nothing recorded it.",
        ),
        _cause(
            "comparing_across_apps",
            "Comparing elsewhere",
            0.05,
            "The cart is a bookmark while they check a competitor.",
        ),
    ),
    likelihoods={
        "price_sensitivity_at_checkout": {
            "dropped_at_method_select": 0.55,
            "high_session_duration": 0.70,
            "cart_value_above_1000": 0.75,
            "dropped_at_otp": 0.08,
            "dropped_at_3ds": 0.05,
        },
        "distracted_multitasking": {
            "dropped_at_method_select": 0.40,
            "high_session_duration": 0.15,
            "first_time_abandonment": 0.70,
            "dropped_at_otp": 0.20,
        },
        "trust_issue_at_checkout": {
            "dropped_at_3ds": 0.65,
            "dropped_at_otp": 0.45,
            "returning_customer": 0.10,
            "high_session_duration": 0.55,
        },
        "payment_method_unavailable": {
            "dropped_at_method_select": 0.85,
            "returning_customer": 0.55,
            "dropped_at_otp": 0.03,
            "dropped_at_3ds": 0.02,
        },
        "technical_failure_unlogged": {
            "dropped_at_otp": 0.50,
            "dropped_at_3ds": 0.45,
            "first_time_abandonment": 0.65,
            "high_session_duration": 0.30,
        },
        "comparing_across_apps": {
            "high_session_duration": 0.80,
            "cart_value_above_1000": 0.70,
            "dropped_at_method_select": 0.50,
        },
    },
)


# ── Failed payment ─────────────────────────────────────────────────────
# One-off charge failures. The decline code carries most of the signal; the
# network view is what separates "this card is bad" from "this bank is down",
# which no single merchant can tell on their own.

FAILED_PAYMENT = CausalDag(
    playbook="failed_payment",
    nodes=(
        _observable("payment_failed", "Payment failed", 0.99, "The charge did not go through."),
        _observable(
            "insufficient_funds_code", "Insufficient funds code", 0.12, "Declined for balance."
        ),
        _observable("card_expired_code", "Card expired code", 0.05, "The instrument has expired."),
        _observable(
            "authentication_failed_code",
            "Authentication failed",
            0.15,
            "The customer never completed the bank's step.",
        ),
        _observable(
            "gateway_timeout_code",
            "Gateway timeout",
            0.10,
            "Nobody answered in time — the rail, not the customer.",
        ),
        _observable(
            "card_blocked_code", "Card blocked", 0.04, "The issuer has frozen the instrument."
        ),
        _observable(
            "bank_downtime_signal",
            "Bank degraded on the network",
            0.04,
            "Cross-merchant statistics show this rail failing right now.",
        ),
        _observable(
            "night_hour_attempt",
            "Attempted overnight",
            0.20,
            "Between 9pm and 6am, when bank batch windows run.",
        ),
        _observable("upi_method", "Paid by UPI", 0.45, "The attempt was on the UPI rail."),
        _cause(
            "issuer_transient_failure",
            "Issuer transient failure",
            0.35,
            "The issuing bank failed this attempt and would take the next one.",
        ),
        _cause(
            "insufficient_funds", "Insufficient funds", 0.25, "There was not enough in the account."
        ),
        _cause("card_expired", "Card expired", 0.15, "The card on file needs replacing."),
        _cause(
            "upi_psp_timeout",
            "UPI PSP timeout",
            0.10,
            "The payment service provider did not respond in time.",
        ),
        _cause(
            "bank_downtime",
            "Bank downtime",
            0.10,
            "The rail is down for everyone, not just this customer.",
        ),
        _cause("card_blocked", "Card blocked", 0.05, "The issuer has frozen the instrument."),
    ),
    likelihoods={
        "issuer_transient_failure": {
            "authentication_failed_code": 0.45,
            "gateway_timeout_code": 0.30,
            "night_hour_attempt": 0.40,
            "insufficient_funds_code": 0.05,
            "card_expired_code": 0.02,
            "card_blocked_code": 0.02,
            # Deliberately low. A single issuer having a bad minute is not a
            # network-visible outage, and this is the likelihood that decides
            # whether the network signal can outvote a much larger prior.
            "bank_downtime_signal": 0.10,
        },
        "insufficient_funds": {
            "insufficient_funds_code": 0.94,
            "authentication_failed_code": 0.03,
            "gateway_timeout_code": 0.02,
            "card_expired_code": 0.01,
            "card_blocked_code": 0.02,
            "bank_downtime_signal": 0.03,
        },
        "card_expired": {
            "card_expired_code": 0.93,
            "insufficient_funds_code": 0.02,
            "authentication_failed_code": 0.05,
            "upi_method": 0.10,
            "bank_downtime_signal": 0.03,
        },
        "upi_psp_timeout": {
            "upi_method": 0.98,
            "gateway_timeout_code": 0.70,
            "authentication_failed_code": 0.20,
            "insufficient_funds_code": 0.03,
            "card_expired_code": 0.01,
            "bank_downtime_signal": 0.15,
        },
        "bank_downtime": {
            "bank_downtime_signal": 0.90,
            "gateway_timeout_code": 0.55,
            "authentication_failed_code": 0.35,
            "night_hour_attempt": 0.45,
            "insufficient_funds_code": 0.03,
            "card_expired_code": 0.01,
        },
        "card_blocked": {
            "card_blocked_code": 0.88,
            "authentication_failed_code": 0.25,
            "insufficient_funds_code": 0.05,
            "card_expired_code": 0.03,
        },
    },
)


# ── B2B overdue ────────────────────────────────────────────────────────
# The distinction that decides the whole approach: a business that always pays
# late and always pays needs a different message from one that has never been
# late before, and chasing the first like the second costs the relationship.

B2B_OVERDUE = CausalDag(
    playbook="b2b_overdue",
    nodes=(
        _observable("days_overdue_above_30", "More than 30 days late", 0.35, ""),
        _observable("days_overdue_above_60", "More than 60 days late", 0.15, ""),
        _observable(
            "always_paid_eventually",
            "Has always paid, eventually",
            0.40,
            "Every previous invoice settled, just not on time.",
        ),
        _observable(
            "first_time_late", "Late for the first time", 0.20, "No history of paying late."
        ),
        _observable(
            "invoice_disputed_flag", "Invoice queried", 0.08, "They have raised a question on it."
        ),
        _observable(
            "partial_payment_made",
            "Paid part of it",
            0.12,
            "Money has moved — the intent is not in question.",
        ),
        _observable("large_invoice_value", "Large invoice", 0.30, "Above their usual ticket size."),
        _observable(
            "no_response_to_reminders",
            "No reply to reminders",
            0.25,
            "Chased, and heard nothing back.",
        ),
        _cause(
            "chronic_late_payment_pattern",
            "Chronic late payer",
            0.45,
            "This is simply how they pay. The money arrives; the date never does.",
        ),
        _cause(
            "invoice_dispute_likely",
            "Disputed invoice",
            0.15,
            "Something on the invoice is being questioned.",
        ),
        _cause(
            "cash_flow_stress_new",
            "New cash-flow stress",
            0.20,
            "A business that used to pay on time has stopped being able to.",
        ),
        _cause(
            "ap_process_delay",
            "Accounts-payable delay",
            0.15,
            "Nobody objects; it is stuck in someone's approval queue.",
        ),
        _cause("unknown", "Unexplained", 0.05, "Nothing on file distinguishes a cause."),
    ),
    likelihoods={
        "chronic_late_payment_pattern": {
            "always_paid_eventually": 0.90,
            "days_overdue_above_30": 0.65,
            "first_time_late": 0.02,
            "invoice_disputed_flag": 0.03,
            "no_response_to_reminders": 0.35,
        },
        "invoice_dispute_likely": {
            "invoice_disputed_flag": 0.85,
            "partial_payment_made": 0.40,
            "large_invoice_value": 0.60,
            "always_paid_eventually": 0.30,
            "days_overdue_above_60": 0.35,
        },
        "cash_flow_stress_new": {
            "first_time_late": 0.70,
            "days_overdue_above_60": 0.45,
            "partial_payment_made": 0.45,
            "no_response_to_reminders": 0.55,
            "always_paid_eventually": 0.20,
        },
        "ap_process_delay": {
            "days_overdue_above_30": 0.55,
            "first_time_late": 0.40,
            "large_invoice_value": 0.55,
            "no_response_to_reminders": 0.20,
            "invoice_disputed_flag": 0.05,
            "days_overdue_above_60": 0.10,
        },
    },
)


DAGS: dict[str, CausalDag] = {
    "subscription_failure": SUBSCRIPTION_FAILURE,
    "checkout_abandonment": CHECKOUT_ABANDONMENT,
    "failed_payment": FAILED_PAYMENT,
    "b2b_overdue": B2B_OVERDUE,
}


def get_dag(playbook: str) -> CausalDag | None:
    """The graph for one playbook, or None if it has no graph."""
    return DAGS.get(playbook)
