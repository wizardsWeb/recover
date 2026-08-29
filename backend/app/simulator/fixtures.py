"""Persona fixture data for the demo simulator.

Every value here traces back to ``scenarios.md``, which is the single source of
truth for the demo. Where a field is needed by the schema but not stated in the
script, it is derived and the derivation is noted in a comment — nothing is
invented silently.

Conventions:

* **All money is in paise** (the schema's ``_cents`` columns), so ₹2,999 is
  ``299900``. India's smallest unit shares the column name with the rest of the
  world's cents; the column name is Phase 1's and is frozen.
* **All timestamps are ISO 8601 with the +05:30 offset.** The demo is set in
  Asia/Kolkata and the scripted times matter (S3 turns on it being 11:34pm on a
  Saturday), so they are written out literally rather than computed.
* ``metadata.true_willingness_to_pay`` and friends are *ground truth the agent
  must never see*. They exist so Phase 9 can score its uplift model against a
  known counterfactual. Nothing in the agent path may read them.
"""

from typing import Any

from app.config import get_settings

# ---------------------------------------------------------------------------
# Merchant slugs used in webhook payloads.
#
# scenarios.md writes `"merchant_id": "zenith_learning"` inside the event JSON.
# That is the merchant's own identifier in *their* system, not our UUID primary
# key — the same distinction as customers.external_id. Keeping the slug in the
# payload is what makes a generated event match the script byte for byte.
# ---------------------------------------------------------------------------

MERCHANT_ZENITH = "zenith_learning"
MERCHANT_KAJAL = "kajal_and_co"
MERCHANT_SHARMA = "sharma_distributors"


# ---------------------------------------------------------------------------
# S1 — Suresh Iyer (Zenith Learning, subscription)
# ---------------------------------------------------------------------------

def demo_customer_id() -> str:
    """Suresh's customer id — the real one when the dashboard has been set up.

    S1 is the only scenario that can be driven by a genuine Razorpay
    subscription, and doing so requires our customer row and Razorpay's customer
    to share an ``external_id``: that string is what the webhook receiver looks a
    settlement up by. Reading it from settings rather than editing this literal
    means setting up the real demo is an env var, not a code change — and a code
    change is the kind of thing that gets committed by accident and then breaks
    every other environment.
    """
    return get_settings().RAZORPAY_DEMO_CUSTOMER_ID or "cust_suresh_iyer"


def demo_subscription_id() -> str:
    """Suresh's subscription id. Same reasoning as `demo_customer_id`."""
    return get_settings().RAZORPAY_DEMO_SUBSCRIPTION_ID or "sub_zenith_aarav_jee"


PERSONA_SURESH: dict[str, Any] = {
    "external_id": demo_customer_id(),
    "name": "Suresh Iyer",
    "phone": "+919812345001",
    "email": "suresh.iyer@example.com",
    "ltv_cents": 2700000,  # ₹27,000
    "tenure_days": 240,  # 8 months
    "consent": {
        "whatsapp": True,
        "sms": True,
        "email": True,
        "marketing": False,
        "opted_out_at": None,
    },
    "metadata": {
        "merchant_slug": MERCHANT_ZENITH,
        "age": 44,
        "city": "Pune",
        "preferred_language": "hinglish",
        "child_name": "Aarav",
        "subscription_purpose": "JEE_coaching",
        "subscription_id": "sub_zenith_aarav_jee",
        "monthly_amount_cents": 299900,
        # Inferred household context — the causal DAG's whole case in S1.
        "inferred_home_loan_emi_day": 1,
        "inferred_salary_credit_day": 7,
        # Ground truth for uplift validation (Phase 9). Never read by the agent.
        "true_willingness_to_pay": 0.94,
        "would_have_recovered_without_intervention": True,
        "would_have_recovered_by_days": 13,  # scenarios.md: 2026-09-14
    },
    "payment_methods": [
        {
            "type": "upi",
            "bin": None,
            "bank": "ICICI",
            # Depressed by three consecutive 1st-of-month failures, not by a
            # bad instrument — the distinction the diagnosis has to make.
            "success_rate_90d": 0.62,
            "metadata": {
                "mandate_id": "mand_icici_suresh_upi",
                "is_autopay_mandate": True,
            },
        }
    ],
    "past_events_summary": {
        "total_charges": 8,
        "recent_failures_on_1st": 3,
        "recent_manual_recoveries": [
            {"date_days_ago": 60, "day_of_month": 7},
            {"date_days_ago": 30, "day_of_month": 4},
            {"date_days_ago": 0, "day_of_month": 8},
        ],
    },
}


# ---------------------------------------------------------------------------
# S2 — Priya Menon (Kajal & Co., checkout abandonment)
# ---------------------------------------------------------------------------

PERSONA_PRIYA: dict[str, Any] = {
    "external_id": "cust_priya_menon",
    "name": "Priya Menon",
    "phone": "+919812345002",
    "email": "priya.menon@example.com",
    # One past order of ₹580 — scenarios.md gives no other purchase history.
    "ltv_cents": 58000,
    "tenure_days": 90,  # first (and only) order was 3 months ago
    "consent": {
        "whatsapp": True,
        "sms": False,
        "email": True,
        "marketing": True,
        "opted_out_at": None,
    },
    "metadata": {
        "merchant_slug": MERCHANT_KAJAL,
        "age": 26,
        "city": "Bangalore",
        "preferred_language": "hinglish",
        "price_sensitivity_score": 0.72,
        "returning_customer": True,
        "past_orders": [{"amount_cents": 58000, "days_ago": 90, "status": "delivered"}],
        # Ground truth for uplift validation (Phase 9).
        # scenarios.md gives this as true_willingness_to_pay_without_intervention.
        "true_willingness_to_pay": 0.18,
        "would_have_recovered_without_intervention": False,
        "would_have_recovered_by_days": None,
    },
    "payment_methods": [
        # She dropped at method selection, so no method was chosen for this
        # cart. These two are what she has on file from the past order plus the
        # UPI handle captured at checkout — the agent needs *something* to
        # reason about when it suggests an alternate rail.
        {
            "type": "upi",
            "bin": None,
            "bank": "HDFC",
            "success_rate_90d": 0.88,
            "metadata": {"is_autopay_mandate": False, "source": "checkout_capture"},
        },
        {
            "type": "card",
            "bin": "512345",
            "bank": "HDFC",
            "success_rate_90d": 0.91,
            "metadata": {"card_type": "debit", "network": "mastercard", "source": "past_order"},
        },
    ],
    "past_events_summary": {
        "total_charges": 1,
        "recent_failures_on_1st": 0,
        "recent_manual_recoveries": [],
    },
}


# ---------------------------------------------------------------------------
# S3 — Aditya Rao (Kajal & Co., failed one-time payment)
# ---------------------------------------------------------------------------

PERSONA_ADITYA: dict[str, Any] = {
    "external_id": "cust_aditya_rao",
    "name": "Aditya Rao",
    "phone": "+919812345003",
    "email": "aditya.rao@example.com",
    "ltv_cents": 380000,  # ₹3,800
    "tenure_days": 420,  # 6 orders over roughly 14 months
    "consent": {
        "whatsapp": True,
        "sms": True,
        "email": True,
        "marketing": False,
        "opted_out_at": None,
    },
    "metadata": {
        "merchant_slug": MERCHANT_KAJAL,
        "age": 32,
        "city": "Hyderabad",
        "preferred_language": "english",
        "past_orders_count": 6,
        "chargebacks": 0,
        # Low across every channel — the reason "send nothing" wins in S3.
        "preferred_channel_engagement": {"whatsapp": 0.4, "email": 0.15, "sms": 0.12},
        # Historical purchase pattern: always weekday mornings/afternoons.
        "typical_purchase_window": "weekday_daytime",
        # Ground truth for uplift validation (Phase 9).
        "true_willingness_to_pay": 0.91,
        "would_have_recovered_without_intervention": True,
        "would_have_recovered_by_days": 2,  # scenarios.md: ~34h, Monday
    },
    "payment_methods": [
        {
            "type": "card",
            "bin": "455673",
            "bank": "HDFC",
            # Healthy instrument; the 11:34pm Saturday failure is the network's
            # weekly degradation, not this card.
            "success_rate_90d": 0.86,
            "metadata": {"card_type": "credit", "network": "visa"},
        },
        {
            "type": "upi",
            "bin": None,
            "bank": "HDFC",
            "success_rate_90d": 0.9,
            "metadata": {"is_autopay_mandate": False, "source": "past_order"},
        },
    ],
    "past_events_summary": {
        "total_charges": 6,
        "recent_failures_on_1st": 0,
        "recent_manual_recoveries": [],
    },
}


# ---------------------------------------------------------------------------
# S4 — Meera Patil (Sharma Distributors, B2B overdue)
# ---------------------------------------------------------------------------

PERSONA_MEERA: dict[str, Any] = {
    "external_id": "cust_meera_rasoi_chain",
    "name": "Meera Patil",
    "phone": "+919812345004",
    "email": "meera.patil@rasoichain.example.com",
    # Derived: 47 past invoices at roughly this invoice's size over 8 years.
    # scenarios.md states the invoice count and the relationship length but not
    # a lifetime figure, so this is an explicit estimate, not a quoted fact.
    "ltv_cents": 681500000,  # ≈ ₹68,15,000
    "tenure_days": 2920,  # 8-year relationship
    "consent": {
        "whatsapp": True,
        "sms": True,
        "email": True,
        "marketing": False,
        "opted_out_at": None,
    },
    "metadata": {
        "merchant_slug": MERCHANT_SHARMA,
        "city": "Delhi",
        "preferred_language": "hinglish",
        "role": "accounts_payable_clerk",
        "company": "Rasoi Chain Pvt Ltd",
        "company_profile": "30-restaurant F&B chain",
        "business_hours_only": True,
        "payer_profile": "chronic_late_but_always_pays",
        "avg_days_late": 18,
        "past_invoices_count": 47,
        "eventual_payment_rate": 1.0,
        "relationship_years": 8,
        "disputes": 0,
        # Ground truth for uplift validation (Phase 9). She always pays; the
        # agent's value is the 8 days it pulls the payment forward, not the
        # payment itself — which is exactly what uplift is supposed to catch.
        "true_willingness_to_pay": 0.97,
        "would_have_recovered_without_intervention": True,
        "would_have_recovered_by_days": 6,  # day 18 of lateness, 12 already elapsed
    },
    "payment_methods": [
        {
            "type": "netbanking",
            "bin": None,
            "bank": "Axis",
            "success_rate_90d": 0.98,
            "metadata": {"settlement_mode": "neft", "is_autopay_mandate": False},
        }
    ],
    "past_events_summary": {
        "total_charges": 47,
        "recent_failures_on_1st": 0,
        "recent_manual_recoveries": [],
    },
}


# ---------------------------------------------------------------------------
# S5 — Vikram Sethi (Zenith Learning, subscription → human handoff)
# ---------------------------------------------------------------------------

PERSONA_VIKRAM: dict[str, Any] = {
    "external_id": "cust_vikram_sethi",
    "name": "Vikram Sethi",
    "phone": "+919812345005",
    "email": "vikram.sethi@example.com",
    "ltv_cents": 3600000,  # ₹36,000 over 18 months — top 8% of the book
    "tenure_days": 547,  # 18 months
    "consent": {
        "whatsapp": True,
        "sms": True,
        "email": True,
        "marketing": False,
        "opted_out_at": None,
    },
    "metadata": {
        "merchant_slug": MERCHANT_ZENITH,
        "preferred_language": "hinglish",
        "child_relation": "daughter",
        "subscription_purpose": "class_9_tuition",
        "subscription_id": "sub_zenith_vikram_class9",
        "monthly_amount_cents": 199900,
        "ltv_percentile": 0.92,
        # First failure in 18 months — which is why the bandit's opening move is
        # a warm payment link rather than anything heavier.
        "prior_failures": 0,
        # Ground truth for uplift validation (Phase 9). He is churning: no
        # message would have recovered this cycle's charge.
        "true_willingness_to_pay": 0.08,
        "would_have_recovered_without_intervention": False,
        "would_have_recovered_by_days": None,
        "churn_intent": True,
    },
    "payment_methods": [
        {
            "type": "upi",
            "bin": None,
            "bank": "HDFC",
            "success_rate_90d": 0.99,
            "metadata": {
                "mandate_id": "mand_hdfc_vikram_upi",
                "is_autopay_mandate": True,
                "mandate_status": "revoked",
            },
        }
    ],
    "past_events_summary": {
        "total_charges": 18,
        "recent_failures_on_1st": 0,
        "recent_manual_recoveries": [],
    },
}


# ---------------------------------------------------------------------------
# S6 — Sana Khatri (Kajal & Co., failed payment → compliance STOP)
# ---------------------------------------------------------------------------

PERSONA_SANA: dict[str, Any] = {
    "external_id": "cust_sana_khatri",
    "name": "Sana Khatri",
    "phone": "+919812345006",
    "email": "sana.khatri@example.com",
    # First-time customer whose only order never completed — nothing earned yet.
    "ltv_cents": 0,
    "tenure_days": 0,
    "consent": {
        # Opted in by default at checkout. She revokes this in the scenario, and
        # the revocation is the whole point of S6.
        "whatsapp": True,
        "sms": True,
        "email": True,
        "marketing": False,
        "opted_out_at": None,
    },
    "metadata": {
        "merchant_slug": MERCHANT_KAJAL,
        "preferred_language": "english",
        "first_time_customer": True,
        "order_value_cents": 68000,
        "order_contents": "lipstick + brush set",
        "consent_source": "checkout_default_opt_in",
        # Ground truth for uplift validation (Phase 9). She is a "do not
        # disturb" case: contacting her destroys value rather than creating it.
        "true_willingness_to_pay": 0.35,
        "would_have_recovered_without_intervention": False,
        "would_have_recovered_by_days": None,
        "opts_out_on_contact": True,
    },
    "payment_methods": [
        {
            "type": "upi",
            "bin": None,
            "bank": "SBI",
            "success_rate_90d": 0.71,
            "metadata": {"is_autopay_mandate": False, "psp": "phonepe"},
        }
    ],
    "past_events_summary": {
        "total_charges": 0,
        "recent_failures_on_1st": 0,
        "recent_manual_recoveries": [],
    },
}


ALL_PERSONAS: list[dict[str, Any]] = [
    PERSONA_SURESH,
    PERSONA_PRIYA,
    PERSONA_ADITYA,
    PERSONA_MEERA,
    PERSONA_VIKRAM,
    PERSONA_SANA,
]

PERSONA_BY_ID: dict[str, dict[str, Any]] = {p["external_id"]: p for p in ALL_PERSONAS}

#: Total payment methods across all six personas — asserted by the loader tests
#: and shown in the simulator's fixture status card.
TOTAL_PAYMENT_METHODS: int = sum(len(p["payment_methods"]) for p in ALL_PERSONAS)


# ---------------------------------------------------------------------------
# B3 — the eight merchants of the federated downtime beat
#
# scenarios.md frames B3 as one bank outage seen across *eight merchants*.
# Phase 2 has exactly one merchant per signed-in user, so the cross-merchant
# aggregate cannot be modelled yet. These eight stand in as eight customers on
# SBI UPI under the current merchant: enough to produce the failure burst the
# network detector will consume, without pretending we have tenancy we don't.
# Phase 10 replaces this with real cross-merchant aggregation.
# ---------------------------------------------------------------------------

_B3_BANKS = ["SBI", "SBI", "SBI", "SBI", "SBI", "SBI", "SBI", "SBI"]
_B3_NAMES = [
    "Rohit Deshmukh",
    "Ananya Bose",
    "Karthik Nair",
    "Farhan Qureshi",
    "Divya Rangan",
    "Manish Gupta",
    "Nikhil Warrier",
    "Shreya Kulkarni",
]
#: Order amounts in paise, spread across a realistic basket range.
_B3_AMOUNTS = [45000, 129900, 68000, 234500, 89900, 156000, 32000, 199000]

B3_SYNTHETIC_CUSTOMERS: list[dict[str, Any]] = [
    {
        "external_id": f"cust_b3_downtime_{index + 1:02d}",
        "name": name,
        "phone": f"+9198123460{index + 1:02d}",
        "email": None,
        "ltv_cents": amount * 3,
        "tenure_days": 120,
        "consent": {
            "whatsapp": True,
            "sms": True,
            "email": False,
            "marketing": False,
            "opted_out_at": None,
        },
        "metadata": {
            "merchant_slug": MERCHANT_KAJAL,
            "is_b3_downtime_cohort": True,
            "order_value_cents": amount,
        },
        "payment_methods": [
            {
                "type": "upi",
                "bin": None,
                "bank": bank,
                # Baseline before the outage: scenarios.md puts SBI UPI at 82%.
                "success_rate_90d": 0.82,
                "metadata": {"is_autopay_mandate": False},
            }
        ],
        "past_events_summary": {
            "total_charges": 3,
            "recent_failures_on_1st": 0,
            "recent_manual_recoveries": [],
        },
        "amount_cents": amount,
    }
    for index, (name, bank, amount) in enumerate(
        zip(_B3_NAMES, _B3_BANKS, _B3_AMOUNTS, strict=True)
    )
]
