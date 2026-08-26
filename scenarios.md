# Recover — Scenarios Script

> **Purpose:** the single source of truth for every demo scenario. This file drives:
> - The seed data for the simulator
> - The test cases for the agent code
> - The script for the video
> - The screenshots for the submission one-pager
>
> **Rule:** every scenario is fully specified — every LLM prompt, every JSON output, every bandit context vector, every WhatsApp message, every dashboard state, every timestamp. If it's not here, it doesn't happen in the demo.

---

## How this file is organized

Each scenario has these sections:
1. **Setup** — who, what, when (merchant, customer, entity state before)
2. **Timeline** — chronological, in agent-clock time (t=0 is the triggering event)
3. **Data payloads** — the actual JSON at each step
4. **Message content** — actual copy of any customer-facing text (usually Hinglish)
5. **Outcome** — what happened, what got recorded
6. **Video beat** — 30-second shot list with VO notes
7. **Simulator seed** — what to preload in the DB to make this scenario runnable

---

## Personas quick reference

| ID | Name | Merchant | Playbook | Story |
|---|---|---|---|---|
| S1 | Suresh Iyer | Zenith Learning | Subscription | Salary-mismatch save via bandit + causal DAG |
| S2 | Priya Menon | Kajal & Co. | Checkout abandonment | Bandit-picked 8% off recovers ₹1,240 cart |
| S3 | Aditya Rao | Kajal & Co. | Failed payment | Silent retry — bandit chose "no message" |
| S4 | Meera Patil | Sharma Distributors | B2B invoice | Hinglish promise-to-pay via LLM classifier |
| S5 | Vikram Sethi | Zenith Learning | Subscription | Graceful human handoff on churn signal |
| S6 | Sana Khatri | Kajal & Co. | Failed payment | STOP reply → hard compliance stop |
| B1 | — | Cross-merchant | System beat | Bandit learning curve over 1,000 cases |
| B2 | — | Cross-merchant | System beat | Uplift ROI: gross vs. incremental recovery |
| B3 | — | Cross-merchant | System beat | Federated SBI UPI downtime detection & pause |

---

# Scenario S1 — Suresh & the salary-mismatch save

**Playbook:** Subscription failure recovery
**Star of the show:** Causal DAG + Contextual Bandit
**Duration in video:** ~18 seconds

## Setup

**Merchant:** Zenith Learning (edtech, JEE coaching subscriptions)
**Customer:** Suresh Iyer, age 44, Pune
- Paying ₹2,999/month for his son Aarav's JEE coaching subscription
- Subscription active for 8 months
- Payment instrument: UPI Autopay mandate on ICICI Bank account
- Household context (inferred): home-loan EMI also on the 1st of each month
- Consent: WhatsApp opt-in, English preferred but Hinglish acceptable

**History (in DB before scenario):**
- Month 1-5: mandate charged successfully on the 1st, always
- Month 6: mandate failed on the 1st (insufficient balance), recovered on the 7th via manual UPI payment
- Month 7: mandate failed on the 1st (insufficient balance), recovered on the 4th via manual UPI payment
- Month 8: mandate failed on the 1st (insufficient balance), recovered on the 8th via manual UPI payment
- Month 9: **this is the scenario**

**Bandit state (at t=0):** Zenith Learning's subscription-playbook bandit has seen ~340 cases. For the context bucket "(ICICI UPI, high-LTV, salary-mismatch-pattern)," it has learned that "retry_at_inferred_date + WhatsApp fallback" has expected reward 0.71, beating "immediate retry" (0.42) and "email dunning only" (0.29).

## Timeline

### t=0 — Event fires
Zenith Learning's subscription cron attempts to charge Suresh's mandate. Fails.

Webhook payload arrives at Recover:
```json
{
  "event": "subscription.charged.failed",
  "merchant_id": "zenith_learning",
  "customer_id": "cust_suresh_iyer",
  "subscription_id": "sub_zenith_aarav_jee",
  "amount": 299900,
  "currency": "INR",
  "failure_code": "BAD_REQUEST_ERROR",
  "failure_reason": "insufficient_funds",
  "method": "upi",
  "mandate_id": "mand_icici_suresh_upi",
  "bank": "ICICI",
  "attempted_at": "2026-09-01T10:32:14+05:30"
}
```

### t=+1s — Case created, enrichment runs
Enrichment layer fetches:
- Customer profile: LTV ₹27,000, 8 months tenure, 3 recent failures on 1st all recovered later
- Bank state: ICICI UPI is healthy right now (network layer confirms 84% success rate)
- Method fingerprint: this mandate has failed on 1st three months running with same failure code
- Population prior: for edtech + parent-payer + ICICI + 1st-of-month failures, the salary-cycle-mismatch pattern posterior is high

### t=+2s — Diagnosis (Causal DAG + LLM)

Causal DAG traversal computes posteriors:
```json
{
  "diagnosis_id": "diag_20260901_103215_suresh",
  "root_cause": "salary_cycle_mismatch_with_competing_emi",
  "posterior_probability": 0.82,
  "causal_path": [
    "subscription.charged.failed",
    "insufficient_funds",
    "account_balance_insufficient_at_charge_time",
    "salary_cycle_mismatch_with_competing_emi"
  ],
  "supporting_evidence": [
    "3 consecutive failures on the 1st with insufficient_funds code",
    "Successful manual payments on days 4, 7, 8 in previous months",
    "Population prior: ICICI account holders with 1st-of-month failures show 71% salary-cycle mismatch pattern"
  ],
  "alternative_hypotheses": [
    {"cause": "mandate_revoked_or_expired", "probability": 0.09},
    {"cause": "account_closed", "probability": 0.04},
    {"cause": "bank_downtime", "probability": 0.03},
    {"cause": "unknown", "probability": 0.02}
  ],
  "risk_factors": [
    "High LTV customer (₹27,000), avoid aggressive tone",
    "Historical pattern shows willingness to pay, just needs timing help",
    "Aarav's coaching is time-sensitive for the child; retention priority is high"
  ],
  "inferred_salary_date": "2026-09-07",
  "confidence_notes": "Inference based on past recovery dates centered around 4-8 of month; likely salary date is 5th-7th"
}
```

### t=+3s — Uplift check

```json
{
  "uplift_estimate": {
    "bucket": "persuadable",
    "estimated_lift": 0.58,
    "expected_incremental_recovery": 173942,
    "cost_of_intervention": 40,
    "verdict": "PROCEED",
    "reasoning": "High-LTV persuadable customer. Without intervention, historical pattern suggests 22% probability of self-service recovery within 15 days. With intervention (retry at inferred salary date + WhatsApp fallback), estimated 80% recovery within 7 days. Net lift is clearly worth the intervention cost."
  }
}
```

### t=+4s — Bandit decides

Bandit context vector (features):
```json
{
  "bank": "ICICI",
  "method": "upi_autopay",
  "hour_of_day": 10,
  "day_of_month": 1,
  "day_of_week": "tuesday",
  "customer_ltv_bucket": "high",
  "customer_tenure_months": 8,
  "past_failures_count": 3,
  "past_recovery_pattern": "manual_on_days_4_to_8",
  "cart_or_charge_amount": 2999,
  "network_bank_health": "healthy",
  "diagnosis_root_cause": "salary_cycle_mismatch_with_competing_emi"
}
```

Bandit output:
```json
{
  "decision_id": "dec_20260901_103218_suresh",
  "chosen_arm": "retry_at_inferred_date_plus_whatsapp_fallback",
  "arm_confidence": 0.71,
  "mode": "exploit",
  "expected_recovery_probability": 0.80,
  "alternatives_considered": [
    {"arm": "retry_at_inferred_date_plus_whatsapp_fallback", "expected_reward": 0.80, "chosen": true},
    {"arm": "immediate_retry_then_whatsapp", "expected_reward": 0.42, "not_chosen_reason": "immediate retry known to fail for this pattern"},
    {"arm": "whatsapp_payment_link_now", "expected_reward": 0.61, "not_chosen_reason": "customer hasn't been paid yet; nudging now may create friction"},
    {"arm": "email_dunning_sequence", "expected_reward": 0.29, "not_chosen_reason": "low channel engagement in customer's history"},
    {"arm": "human_handoff", "expected_reward": 0.55, "not_chosen_reason": "not warranted; bandit-selected action expected to work"}
  ],
  "action_params": {
    "scheduled_retry_date": "2026-09-07T09:00:00+05:30",
    "fallback_channel": "whatsapp",
    "fallback_trigger": "on_retry_failure",
    "message_tone": "warm_reassuring_hinglish"
  }
}
```

### t=+5s — Guardrail check

```json
{
  "checks": {
    "rbi_retry_count_within_cycle": {"pass": true, "current_count": 1, "max": 3},
    "rbi_time_since_last_retry": {"pass": true, "hours_elapsed": 720},
    "trai_message_frequency": {"pass": true, "messages_last_24h": 0, "cap": 2},
    "trai_time_of_day": {"pass": true, "current_hour_local": 10, "quiet_hours": "21-09"},
    "consent_whatsapp": {"pass": true},
    "consent_optout": {"pass": true, "opted_out": false},
    "merchant_playbook_active": {"pass": true},
    "network_bank_status": {"pass": true, "bank": "ICICI", "status": "healthy"}
  },
  "verdict": "PROCEED"
}
```

### t=+6s — Execution scheduled

Two things scheduled:
1. Retry the mandate charge at 2026-09-07T09:00:00+05:30
2. Contingent WhatsApp send if retry fails

No customer-facing action taken yet. Case moves to `status: scheduled`.

### t=+6 days — Retry executes (2026-09-07 09:00)

Retry API call:
```json
{
  "action": "subscription.retry_charge",
  "subscription_id": "sub_zenith_aarav_jee",
  "idempotency_key": "retry_20260907_suresh"
}
```

Response: `success`, ₹2,999 charged.

### t=+6 days + 5s — Learn step
- Reward posted: recovered = 1, amount = 2999
- Bandit updates arm posterior for context bucket
- Causal DAG confirms salary_cycle_mismatch edge, increments transition count
- Uplift model records: intervention_taken=true, outcome=recovered, added to training set
- Federated layer: anonymized (ICICI, upi_autopay, retry_at_inferred_date, recovered) tuple pushed

## Outcome

- Amount at risk: ₹2,999
- Amount recovered: ₹2,999
- Time to recovery: 6 days
- Messages sent: 0 (silent recovery, no customer annoyance)
- Cost of recovery: ~₹0 (just an API retry)
- Customer LTV preserved: ₹27,000+
- Bandit reward: +1.0 on chosen arm

## Video beat

**Duration:** 18 seconds
**Screen composition:** merchant dashboard on left (Zenith Learning), causal DAG visualization on right

- **[0:00]** Ping sound. Toast pops: "New case: Suresh Iyer, ₹2,999 mandate failed"
- **[0:03]** Case detail view opens. Causal DAG on the right lights up node-by-node, ending on `salary_cycle_mismatch_with_competing_emi (0.82)`
- **[0:07]** Bandit panel slides in: chosen arm highlighted, alternatives fan out with their expected rewards
- **[0:11]** Timeline shows: "Retry scheduled for Sep 7, 09:00 — no message sent"
- **[0:14]** Time fast-forwards (visual: calendar spinning), Sep 7 arrives, retry succeeds, green checkmark
- **[0:17]** Case closes, LTV preserved badge appears

**Voiceover:**
> *"Suresh's mandate failed on the 1st — again. Our causal graph traced it in seconds: salary cycle mismatched with his home loan EMI. The bandit picked the smart move — wait until the 7th when his salary arrives, don't spam him. Recovered without sending a single message."*

## Simulator seed

```yaml
customer:
  id: cust_suresh_iyer
  merchant: zenith_learning
  name: Suresh Iyer
  age: 44
  city: Pune
  ltv: 27000
  tenure_months: 8
  consent: {whatsapp: true, sms: true, email: true, marketing: false}
  metadata:
    preferred_language: hinglish
    child_name: Aarav
    subscription_purpose: JEE_coaching

payment_history:
  - month: 1-5, day: 1, status: success
  - month: 6, day: 1, status: failed
  - month: 6, day: 7, status: manual_success
  - month: 7, day: 1, status: failed
  - month: 7, day: 4, status: manual_success
  - month: 8, day: 1, status: failed
  - month: 8, day: 8, status: manual_success

trigger_event:
  at: 2026-09-01T10:32:14+05:30
  type: subscription.charged.failed
  ...

true_willingness_to_pay: 0.94  # ground truth for uplift validation
would_have_recovered_without_intervention: true
would_have_recovered_by: 2026-09-14  # ~13 days later, on his own
```

---

# Scenario S2 — Priya & the cart abandonment recovery

**Playbook:** Checkout abandonment
**Star of the show:** Bandit picks optimal discount magnitude + LLM Hinglish message
**Duration in video:** ~16 seconds

## Setup

**Merchant:** Kajal & Co. (D2C beauty)
**Customer:** Priya Menon, age 26, Bangalore
- Cart contents: Vitamin C serum (₹640), Moisturizer (₹420), SPF 50 sunscreen (₹280) = ₹1,340 subtotal, ₹1,240 with existing 7% discount
- Dropped at checkout, method-selection stage
- Browsing time before drop: 4 minutes 12 seconds
- Signed-in customer, has previously bought once (₹580 order 3 months ago, delivered, no return)
- Consent: WhatsApp opt-in, English + Hinglish comfortable

**Bandit state:** Kajal's checkout-abandonment bandit has seen ~180 cases and has learned that for the context bucket "(returning customer, cart ₹1,000-1,500, dropped at method-select, high engagement)," an 8% discount code + WhatsApp saved cart link is the optimal arm (expected reward 0.62), beating 5% (0.48), 12% (0.58 but margin-negative), no-discount-just-nudge (0.31).

## Timeline

### t=0 — Event fires
```json
{
  "event": "checkout.abandoned",
  "merchant_id": "kajal_and_co",
  "customer_id": "cust_priya_menon",
  "cart_id": "cart_20260903_priya",
  "cart_value": 124000,
  "currency": "INR",
  "items": [
    {"sku": "vc_serum_30ml", "name": "Vitamin C serum", "price": 64000, "qty": 1},
    {"sku": "hydra_moisturizer_50g", "name": "Hydra moisturizer", "price": 42000, "qty": 1},
    {"sku": "spf50_sunscreen_60ml", "name": "SPF 50 sunscreen", "price": 28000, "qty": 1}
  ],
  "dropoff_stage": "method_selection",
  "session_duration_seconds": 252,
  "abandoned_at": "2026-09-03T20:14:33+05:30"
}
```

### t=+2s — Diagnosis
```json
{
  "root_cause": "price_sensitivity_at_checkout",
  "posterior_probability": 0.74,
  "causal_path": [
    "checkout.abandoned",
    "dropped_at_method_selection",
    "no_technical_failure_signal",
    "price_sensitivity_at_checkout"
  ],
  "supporting_evidence": [
    "4+ minute browsing session (high intent)",
    "Returning customer (not trust issue)",
    "Dropped at method-select not OTP (not payment tech issue)",
    "Cart 2x her past order size"
  ],
  "alternative_hypotheses": [
    {"cause": "distracted_multitasking", "probability": 0.14},
    {"cause": "comparing_across_apps", "probability": 0.09},
    {"cause": "technical_issue_unlogged", "probability": 0.03}
  ],
  "risk_factors": []
}
```

### t=+3s — Uplift check
```json
{
  "bucket": "persuadable",
  "estimated_lift": 0.44,
  "expected_incremental_recovery": 54560,
  "cost_of_intervention": 12,
  "verdict": "PROCEED"
}
```

### t=+4s — Bandit decides
```json
{
  "chosen_arm": "whatsapp_saved_cart_plus_8pct_discount",
  "arm_confidence": 0.62,
  "mode": "exploit",
  "expected_recovery_probability": 0.62,
  "alternatives_considered": [
    {"arm": "whatsapp_saved_cart_plus_8pct_discount", "expected_reward": 0.62, "chosen": true},
    {"arm": "whatsapp_saved_cart_no_discount", "expected_reward": 0.31, "not_chosen_reason": "insufficient nudge for price-sensitive segment"},
    {"arm": "whatsapp_plus_5pct_discount", "expected_reward": 0.48, "not_chosen_reason": "under-discounted for this cart size"},
    {"arm": "whatsapp_plus_12pct_discount", "expected_reward": 0.58, "not_chosen_reason": "recovery marginally lower AND margin-negative"},
    {"arm": "email_only_saved_cart", "expected_reward": 0.19, "not_chosen_reason": "low engagement in past"}
  ],
  "action_params": {
    "channel": "whatsapp",
    "discount_pct": 8,
    "discount_code": "PRIYA8",
    "cart_link_expiry_hours": 24
  }
}
```

### t=+5s — Guardrail check
All checks pass. Priya has received 0 messages in last 24h; not in quiet hours; opt-in confirmed; within merchant discount cap of 15%.

### t=+6s — LLM generates message

LLM message-generation call output:
```json
{
  "channel": "whatsapp",
  "template_id": "kajal_cart_recovery_hinglish_v2",
  "text": "Hi Priya! 💕 Aapke cart mein Vitamin C serum + moisturizer + sunscreen wait kar rahe hain ✨\n\nAaj hi complete karo, aur flat 8% off — code: PRIYA8\n\n👉 [cart link]\n\nOffer sirf 24 hours ke liye. Miss mat karna!",
  "generation_reasoning": "Warm, casual Hinglish for young beauty consumer segment. Emoji use matches Kajal & Co. brand voice. Specific product mention reinforces desire. Time-bound offer creates urgency without being pushy."
}
```

### t=+7s — Execution

WhatsApp Business API call fires. Message delivered at t=+9s.

### t=+2m 14s — Priya opens the message

Read receipt registered.

### t=+8m 32s — Priya clicks the cart link

Cart page opens with 8% discount pre-applied. Total now ₹1,141.

### t=+12m 07s — Priya completes checkout

Payment succeeds via UPI. ₹1,141 recovered.

### t=+12m 12s — Learn step
- Bandit reward: recovered = 1, amount = 1141, revenue_after_discount_cost = 1141 (vs. counterfactual 0)
- Discount magnitude was optimal per bandit's prior — reinforces the 8% arm for this context
- Federated layer: (Kajal & Co., checkout_abandonment, returning_customer, ₹1200-bucket, 8pct_discount, recovered) tuple pushed

## Outcome

- Amount at risk: ₹1,240
- Amount recovered: ₹1,141
- Discount cost: ₹99 (7.9%)
- Time to recovery: 12 minutes
- Bandit reward: +1.0 on chosen arm
- Merchant net revenue vs. lost cart: +₹1,141

## Video beat

**Duration:** 16 seconds
**Screen composition:** Priya's phone (WhatsApp) on left, Kajal & Co. dashboard on right

- **[0:00]** Toast: "Cart abandoned — ₹1,240 — Priya Menon"
- **[0:03]** Bandit panel shows the discount ladder — 5% / 8% / 12% — with 8% highlighted as the winner, expected reward numbers visible
- **[0:07]** WhatsApp on the left animates typing dots, then the Hinglish message renders in a real WhatsApp bubble
- **[0:11]** Fast-forward: Priya taps the link, cart opens with discount applied, checkout success
- **[0:14]** Dashboard registers: "Recovered ₹1,141 in 12 min"

**Voiceover:**
> *"Priya abandoned a ₹1,240 skincare cart. The bandit knows: for this segment, 8% off is the sweet spot — not 5, not 12. Message written in her language, cart back in her hands, ₹1,141 recovered in twelve minutes."*

## Simulator seed
```yaml
customer:
  id: cust_priya_menon
  merchant: kajal_and_co
  name: Priya Menon
  age: 26
  city: Bangalore
  past_orders: [{amount: 580, days_ago: 90, status: delivered}]
  consent: {whatsapp: true, sms: false, email: true, marketing: true}
  metadata:
    preferred_language: hinglish
    price_sensitivity_score: 0.72

true_willingness_to_pay_without_intervention: 0.18
would_have_recovered_without_intervention: false
```

---

# Scenario S3 — Aditya & the silent retry

**Playbook:** Failed one-time payment
**Star of the show:** Bandit's *restraint* + Network Intelligence timing
**Duration in video:** ~15 seconds

## Setup

**Merchant:** Kajal & Co.
**Customer:** Aditya Rao, age 32, Hyderabad
- Placed order for ₹840 (face wash + lip balm gift set)
- Paid via HDFC credit card
- Payment failed at 11:34pm on Saturday
- Failure code: `AUTHENTICATION_FAILED` (issuer OTP flow timed out)
- Long-time customer, 6 past orders, never a chargeback

**Bandit state:** For context bucket "(HDFC credit card, weekend late-night, returning customer, ₹500-1000 cart)," bandit has learned: silent retry Monday 9am has 0.78 expected reward; late-night WhatsApp has 0.34 (customer sleeping); morning email has 0.41. Bandit strongly prefers silent retry.

**Network intelligence state:** HDFC credit card current-hour success rate is 34% — normal weekend-night degradation, not downtime. Monday 9am historical success is 78%.

## Timeline

### t=0 — Event fires (2026-09-06T23:34:12+05:30 — Saturday)
```json
{
  "event": "payment.failed",
  "merchant_id": "kajal_and_co",
  "customer_id": "cust_aditya_rao",
  "order_id": "order_20260906_aditya",
  "amount": 84000,
  "currency": "INR",
  "method": "card",
  "card": {"issuer": "HDFC", "type": "credit", "network": "visa", "bin": "455673"},
  "failure_code": "AUTHENTICATION_FAILED",
  "failure_reason": "issuer_otp_timeout",
  "attempted_at": "2026-09-06T23:34:12+05:30"
}
```

### t=+1s — Enrichment + network check
- Aditya has 6 past successful payments, all HDFC credit card, all on weekday mornings/afternoons
- Network layer: HDFC credit card success rate in last hour = 34% (normal weekend-night degradation, ~150 sample size across merchants)
- Network layer: predicted Monday 9am success rate = 78% (based on trailing 4 weeks)

### t=+2s — Diagnosis
```json
{
  "root_cause": "issuer_transient_failure_normal_degradation",
  "posterior_probability": 0.71,
  "causal_path": [
    "payment.failed",
    "authentication_failed",
    "issuer_otp_flow_timeout",
    "issuer_transient_failure_normal_degradation"
  ],
  "supporting_evidence": [
    "HDFC weekend-night success rate is 34% (network-wide, healthy at other hours)",
    "Customer has 6 successful past HDFC payments (not card-side issue)",
    "OTP timeout suggests bank IVR/2FA flow issue, not decline"
  ],
  "alternative_hypotheses": [
    {"cause": "customer_lost_otp_intentionally_abandoning", "probability": 0.14},
    {"cause": "card_being_replaced", "probability": 0.08},
    {"cause": "insufficient_credit", "probability": 0.07}
  ]
}
```

### t=+3s — Uplift check
```json
{
  "bucket": "sure_thing_if_timed_right",
  "estimated_lift_silent_retry_monday": 0.63,
  "estimated_lift_late_night_message": 0.09,
  "verdict": "PROCEED with silent retry only",
  "reasoning": "Customer will pay if retried at the right time. A message right now would annoy without lifting recovery — negative net utility."
}
```

### t=+4s — Bandit decides
```json
{
  "chosen_arm": "silent_retry_monday_9am_no_message",
  "arm_confidence": 0.78,
  "mode": "exploit",
  "expected_recovery_probability": 0.78,
  "alternatives_considered": [
    {"arm": "silent_retry_monday_9am_no_message", "expected_reward": 0.78, "chosen": true},
    {"arm": "immediate_retry_now", "expected_reward": 0.34, "not_chosen_reason": "network confirms current hour has 34% success — retrying now wastes an attempt"},
    {"arm": "whatsapp_now", "expected_reward": 0.09, "not_chosen_reason": "customer likely sleeping, 11:34pm; message would annoy"},
    {"arm": "email_now", "expected_reward": 0.19, "not_chosen_reason": "customer doesn't engage with email historically"},
    {"arm": "sms_now", "expected_reward": 0.11, "not_chosen_reason": "same as WhatsApp — sleeping"},
    {"arm": "morning_email_then_retry", "expected_reward": 0.53, "not_chosen_reason": "adds friction without adding recovery"}
  ],
  "action_params": {
    "scheduled_retry": "2026-09-08T09:00:00+05:30",
    "no_customer_communication": true,
    "reasoning": "Bandit prefers minimum-intrusion approach"
  }
}
```

### t=+5s — Guardrail check
All pass. Special note: TRAI quiet-hours check would have blocked messaging anyway (currently 11:34pm) — bandit's choice is aligned with compliance.

### t=+6s — Retry scheduled, no message
Case status: `scheduled`.

### t=+1 day 9h 26m — Retry executes (2026-09-08 09:00, Monday)
Payment succeeds. ₹840 recovered.

### Learn step
- Bandit reward: +1.0 on `silent_retry_monday_9am_no_message`
- Network layer updated: (HDFC credit card, Monday 9am) success stat count incremented

## Outcome

- Amount at risk: ₹840
- Amount recovered: ₹840
- Time to recovery: ~34 hours
- Messages sent: 0
- Customer annoyance: 0
- Bandit reward: +1.0

## Video beat

**Duration:** 15 seconds
**Screen composition:** Network Intelligence heatmap on left, case detail on right

- **[0:00]** Toast: "Payment failed — Aditya Rao — HDFC card"
- **[0:03]** Network Intelligence panel highlights: HDFC card × Sat 11pm cell glowing amber (34%); Monday 9am cell glowing green (78%)
- **[0:07]** Bandit alternatives fan out; camera zooms in on "whatsapp_now" and "silent_retry_monday" — the former grayed out with "would annoy" label, the latter highlighted
- **[0:10]** Timeline: "Scheduled: silent retry Monday 09:00. No message sent."
- **[0:13]** Fast-forward, Monday arrives, retry succeeds.

**Voiceover:**
> *"Aditya's card failed at 11:34pm Saturday. Our network sees HDFC's weekend-night degradation happens every week. The smartest move? Wait for Monday morning. Don't wake him up. ₹840 recovered — zero messages sent."*

## Simulator seed
```yaml
customer:
  id: cust_aditya_rao
  merchant: kajal_and_co
  name: Aditya Rao
  ltv: 3800
  past_orders_count: 6
  preferred_channel_engagement:
    whatsapp: 0.4
    email: 0.15
    sms: 0.12
  consent: {whatsapp: true, sms: true, email: true, marketing: false}

network_state_at_event:
  hdfc_credit_card_hour_23_success_rate: 0.34
  hdfc_credit_card_monday_9am_success_rate: 0.78

true_willingness_to_pay: 0.91
would_have_recovered_without_intervention: true
would_have_recovered_by: 2026-09-08  # ~34h, same day Monday
```

---

# Scenario S4 — Meera & the B2B promise-to-pay

**Playbook:** B2B overdue invoices
**Star of the show:** LLM Hinglish reply classification + promise-to-pay tracker
**Duration in video:** ~22 seconds

## Setup

**Merchant:** Sharma Distributors (F&B/FMCG distributor, Delhi)
**Customer:** Meera Patil, AP clerk at Rasoi Chain Pvt Ltd (30-restaurant F&B chain)
- Outstanding invoice INV-2026-08847: ₹1,45,000 for 60 crates of cooking oil
- Due date: 2026-08-20
- Today: 2026-09-01 (12 days overdue)
- Payment history: chronic-late payer, average 18 days late, but always pays in full over 8-year relationship
- Consent: WhatsApp opt-in, business hours only

**Bandit state:** For context "(chronic-late payer, ₹1L-2L invoice, 10-15 days overdue, F&B vertical)," bandit prefers: polite-reminder → firm-reminder (day 5 gap) → partial-payment-offer (day 10 gap). Straight escalation to human has lower reward (0.38 vs. 0.68 for graduated sequence).

## Timeline

### Day 12 (2026-09-01) — Case activated by cron
```json
{
  "event": "invoice.overdue",
  "merchant_id": "sharma_distributors",
  "customer_id": "cust_meera_rasoi_chain",
  "invoice_id": "INV-2026-08847",
  "amount": 14500000,
  "currency": "INR",
  "due_date": "2026-08-20",
  "days_overdue": 12,
  "invoice_items": "60 crates cooking oil (Fortune sunflower)"
}
```

### Diagnosis
```json
{
  "root_cause": "chronic_late_payment_pattern_normal_ap_cycle",
  "posterior_probability": 0.87,
  "supporting_evidence": [
    "8-year relationship, 100% eventual payment rate",
    "Average lateness 18 days across 47 past invoices",
    "No red flags: no recent unusual patterns, no partial payments, no disputes"
  ],
  "alternative_hypotheses": [
    {"cause": "cash_flow_stress_new", "probability": 0.09},
    {"cause": "invoice_dispute_unlogged", "probability": 0.03}
  ]
}
```

### Uplift check
```json
{
  "bucket": "persuadable",
  "estimated_lift": 0.31,
  "expected_incremental_days_saved": 8,
  "verdict": "PROCEED with graduated sequence"
}
```

### Bandit picks the graduated sequence
```json
{
  "chosen_arm": "graduated_b2b_sequence",
  "action_params": {
    "day_12": "polite_reminder_whatsapp",
    "day_17": "firm_reminder_whatsapp_plus_email",
    "day_22": "partial_payment_offer",
    "day_27": "escalate_to_human_ar"
  }
}
```

### Day 12 — Polite reminder sent

LLM-generated Hinglish WhatsApp:
> Hi Meera ji, hope you're well 🙏
>
> Just a gentle reminder — invoice INV-2026-08847 (₹1,45,000, 60 crates cooking oil) was due 20th August, ab 12 din ho gaye hain.
>
> Pay karne ke liye ek click: [payment link]
>
> Koi issue ho toh please batayein, hum help kar sakte hain.

No reply from Meera on day 12-16.

### Day 17 — Firm reminder sent (LLM adjusts tone)

WhatsApp:
> Meera ji, following up on invoice INV-2026-08847 (₹1,45,000).
>
> Ye 17 din overdue hai. Please arrange payment by 22nd September, ya humein bata dijiye timeline.
>
> Payment link: [payment link]
>
> Email bhi bheja hai. — Sharma Distributors AR team

Simultaneously: email fires with same content, more formal.

### Day 18, 11:34 AM — Meera replies to WhatsApp

Raw reply:
> boss, 50% abhi kar deti hoon, baaki 25 tak. system mein delay hai. sorry for late.

### LLM classifies reply

```json
{
  "reply_id": "reply_20260918_meera",
  "language": "hinglish",
  "intent": "promise_to_pay",
  "sub_intent": "partial_payment_now_plus_promise_for_remainder",
  "sentiment": "cooperative_apologetic",
  "extracted_entities": {
    "partial_payment_percentage": 50,
    "partial_payment_amount_inferred": 7250000,
    "remainder_promise_date": "2026-09-25",
    "delay_reason_offered": "internal_system_delay"
  },
  "hardship_signal": false,
  "opt_out_signal": false,
  "credibility_score": 0.84,
  "recommended_state_updates": [
    "MARK case as promise_to_pay_active",
    "PAUSE all further reminders until 2026-09-25",
    "CREATE partial payment link for ₹72,500",
    "SCHEDULE follow-up on 2026-09-25 if remainder not received"
  ]
}
```

### t=+3 min — Partial payment link sent

WhatsApp:
> Thank you Meera ji, no worries at all 🙏
>
> 50% (₹72,500) ke liye link: [partial payment link]
>
> Remaining ₹72,500 for 25th September as agreed — hum tab remind kar denge. Take care!

### Day 18, 3:22 PM — Partial payment received

Payment webhook: ₹72,500 received via Payment Link.

Case state updates: `promise_to_pay_active`, remainder due 25th.

### Day 25 — Automated check + gentle reminder

WhatsApp on morning of 25th:
> Good morning Meera ji ☀️
>
> Reminder — remaining ₹72,500 for INV-2026-08847 due today as discussed.
>
> Link: [payment link]
>
> Kindly arrange. Thank you!

### Day 25, 4:47 PM — Remainder paid

Full invoice recovered.

## Outcome

- Amount at risk: ₹1,45,000
- Amount recovered: ₹1,45,000 (100%)
- Time to first payment: 18 days (vs. historical average 18 days = met expectation)
- Time to full recovery: 25 days (vs. historical 22 days = slightly slower, but reduced disputes)
- Messages sent: 4 (well within TRAI + merchant caps)
- Escalation to human: no (bandit sequence + LLM reply handling did it all)
- Promise-to-pay accuracy validated: yes (Meera kept her word)

## Video beat

**Duration:** 22 seconds
**Screen composition:** WhatsApp thread on left, promise-to-pay tracker + case timeline on right

- **[0:00]** Toast: "Overdue invoice — Meera Patil — ₹1,45,000 — Day 12"
- **[0:03]** Bandit picks the graduated sequence; timeline shows the four planned steps
- **[0:06]** Day 12 message renders in WhatsApp bubble (Hinglish, polite)
- **[0:10]** Fast-forward: Day 17 firm reminder renders
- **[0:13]** Meera's reply appears: "boss, 50% abhi kar deti hoon..."
- **[0:15]** LLM classification popup animates in: **intent: promise_to_pay, partial: 50%, promise_date: 25 Sep**
- **[0:18]** Promise-to-pay tracker appears on right with countdown to 25 Sep
- **[0:20]** Fast-forward to 25 Sep, remainder paid, invoice closed

**Voiceover:**
> *"Meera's a great customer — she always pays, just late. When she messaged 'boss, 50% abhi kar deti hoon,' our LLM understood. Split payment accepted, promise date tracked, ₹1,45,000 recovered — no human needed, no relationship damaged."*

---

# Scenario S5 — Vikram & the graceful human handoff

**Playbook:** Subscription failure
**Star of the show:** Agent choosing to STOP and hand off to a human
**Duration in video:** ~14 seconds

## Setup

**Merchant:** Zenith Learning
**Customer:** Vikram Sethi, parent, subscriber for 18 months
- Paying ₹1,999/month for daughter's Class 9 tuition
- LTV: ₹36,000 (very high)
- Consent: WhatsApp opt-in, English/Hinglish

**Context:** mandate failed for the first time in 18 months. Bandit's first choice: WhatsApp Payment Link (bandit reasoning: high-LTV, first-ever failure, likely oversight or method issue).

## Timeline

### t=0 — Mandate failure event
```json
{
  "event": "subscription.charged.failed",
  "customer_id": "cust_vikram_sethi",
  "amount": 199900,
  "failure_reason": "mandate_revoked",
  "attempted_at": "2026-09-04T08:15:00+05:30"
}
```

### Diagnosis + Uplift + Bandit

Diagnosis says `mandate_revoked_by_customer_at_bank_end`, posterior 0.62. Bandit picks WhatsApp Payment Link with a warm message.

### t=+30s — Message sent

Hinglish WhatsApp:
> Hi Vikram ji 🙏
>
> Aapke Class 9 tuition subscription (₹1,999) ka auto-payment aaj process nahi ho paaya — looks like your UPI mandate got revoked.
>
> No problem — ek click mein pay karo yahaan: [payment link]
>
> Ya reply karein "help" aur hum aapko call kar denge.

### t=+11 min — Vikram replies

> bhaisaab beta ab coaching nahi le raha, cancel kar do please

### LLM classifies

```json
{
  "language": "hinglish",
  "intent": "churn_confirmation",
  "sub_intent": "cancellation_request_child_stopped_service",
  "sentiment": "neutral_definitive",
  "extracted_entities": {"reason": "child_no_longer_using_service"},
  "hardship_signal": false,
  "opt_out_signal": false,
  "churn_signal": true,
  "recommended_state_updates": [
    "STOP all recovery attempts immediately",
    "MARK subscription for cancellation with reason: child_stopped_service",
    "HANDOFF to human retention team with full case + LTV context",
    "DO NOT auto-cancel: let human retention offer alternatives first"
  ]
}
```

### t=+11 min 5s — Agent stops recovery, handoff created

Handoff card generated for Zenith Learning's retention team:
```
─────────────────────────────────
HIGH-LTV CHURN — HUMAN ATTENTION
─────────────────────────────────
Customer: Vikram Sethi
LTV: ₹36,000 over 18 months (top 8%)
Subscription: Class 9 tuition, ₹1,999/mo
Reason given: "beta ab coaching nahi le raha"
Suggested actions:
  • Course pause + resume (3-month hold)
  • Downgrade to test-prep-only tier (₹799)
  • Refer to Class 10 upgrade path (child likely moving up)
Do NOT auto-cancel. Human retention has 48h to reach out.
─────────────────────────────────
```

No further automated recovery attempts.

### t=+2h — Human retention team calls Vikram

(Not in agent scope, but shown as outcome.) Human offers 3-month pause. Vikram accepts. Subscription paused, not cancelled.

## Outcome

- Amount at risk this cycle: ₹1,999
- Amount recovered by agent: ₹0
- Cancellation prevented: yes (paused, not lost)
- LTV preserved for future: ₹36,000+
- Agent's contribution: correctly *stopped* and handed off with full context
- Bandit reward: 0 for this arm (no recovery), but the *handoff* is logged as the right action

## Video beat

**Duration:** 14 seconds
**Screen composition:** WhatsApp on left, dashboard "human handoff" card on right

- **[0:00]** Toast: "Mandate failed — Vikram Sethi — 18-month subscriber (high LTV)"
- **[0:03]** Message sent (WhatsApp bubble renders)
- **[0:06]** Vikram's reply appears: "bhaisaab beta ab coaching nahi le raha..."
- **[0:08]** LLM classification popup: **intent: churn_confirmation, action: STOP + HANDOFF**
- **[0:10]** Dashboard slides in a red-bordered handoff card with LTV, context, and suggested retention offers
- **[0:12]** Timeline: "Agent stopped. Human retention notified. Auto-recovery disabled for this case."

**Voiceover:**
> *"Vikram said cancel. Our agent could have kept trying — but it recognized the signal, stopped immediately, and handed off to a human retention team with full context. Restraint is intelligence. And it saved a ₹36,000 customer."*

---

# Scenario S6 — Sana & the compliance STOP

**Playbook:** Failed one-time payment (initially), then hard compliance stop
**Star of the show:** Instant honoring of opt-out
**Duration in video:** ~10 seconds

## Setup

**Merchant:** Kajal & Co.
**Customer:** Sana Khatri, first-time customer, ₹680 order (lipstick + brush set)
- Payment failed on first attempt (UPI PSP timeout)
- Consent: WhatsApp opt-in by default at checkout

## Timeline

### t=0 — Payment failure event
```json
{
  "event": "payment.failed",
  "customer_id": "cust_sana_khatri",
  "amount": 68000,
  "method": "upi",
  "failure_code": "PSP_TIMEOUT",
  "attempted_at": "2026-09-05T14:22:00+05:30"
}
```

### Bandit picks WhatsApp Payment Link (standard first attempt)

Hinglish WhatsApp:
> Hi Sana! 💄
>
> Aapka order (lipstick + brush set, ₹680) complete nahi hua — koi baat nahi, ek click mein pay karo: [payment link]

### t=+8 min — Sana replies

Raw reply:
> STOP

### LLM classifies

```json
{
  "language": "english",
  "intent": "explicit_opt_out",
  "sentiment": "curt",
  "hardship_signal": false,
  "opt_out_signal": true,
  "opt_out_scope": "all_channels_all_playbooks_permanent",
  "recommended_state_updates": [
    "IMMEDIATELY revoke consent across all channels (WhatsApp, SMS, email marketing)",
    "MARK customer as no_contact",
    "CLOSE this case as consent_revoked",
    "HALT any pending scheduled actions for this customer across all playbooks",
    "LOG compliance action with timestamp"
  ]
}
```

### t=+8 min 4s — Consent revoked, all pending actions halted

- Sana's consent record updated: `whatsapp: false, sms: false, email_marketing: false, opted_out_at: 2026-09-05T14:30:04+05:30`
- Any pending scheduled recovery actions for Sana across any Kajal & Co. playbook are cancelled
- Compliance log entry created with timestamp
- Case closed as `stopped_consent_revoked`

Total time from Sana's "STOP" to full honor: **4 seconds**.

## Outcome

- Amount at risk: ₹680
- Amount recovered: ₹0
- Compliance: 100% honored, 4-second response time
- Future contact: none, ever (unless customer explicitly opts back in)

## Video beat

**Duration:** 10 seconds
**Screen composition:** WhatsApp on left, audit log timeline on right

- **[0:00]** Toast: "Payment failed — Sana Khatri — ₹680"
- **[0:02]** WhatsApp message renders and is sent
- **[0:04]** Sana's reply appears: "STOP"
- **[0:05]** LLM classification: **intent: explicit_opt_out, scope: permanent, all channels**
- **[0:06]** Audit log on the right unfurls in real-time:
  - `14:30:00 — Sana reply received: "STOP"`
  - `14:30:01 — LLM classified: opt_out_signal=true`
  - `14:30:02 — Consent revoked (whatsapp, sms, email_marketing)`
  - `14:30:03 — Pending actions cancelled: 0 actions across 0 playbooks`
  - `14:30:04 — Case closed: stopped_consent_revoked`
- **[0:09]** Big green badge: "Opt-out honored in 4 seconds"

**Voiceover:**
> *"Sana said STOP. Four seconds later — every channel silenced, every future action cancelled, compliance logged. This isn't optional. This is what trust looks like."*

---

# System Beat B1 — The Bandit Learning Curve

**Star of the show:** Contextual bandit learns and beats the LLM-only baseline
**Duration in video:** ~25 seconds

## What we show

A single chart, two lines, x-axis = cases seen (0 to 1000), y-axis = rolling recovery rate.

**Line 1 — LLM-only baseline (grey):**
- Flat at ~22% throughout
- Small annotations: "LLM picks the intuitive action every time; no learning."

**Line 2 — Recover (Bandit + LLM) (green):**
- Starts at ~20% at case 0 (exploration phase)
- Slight dip at cases 30-80 (bandit exploring low-reward arms)
- Crosses baseline at ~case 200
- Steep climb 200-500 (bandit converging on winners)
- Levels at ~38% by case 800

**Annotations along the green line:**
- At case ~140: "Bandit learned: silent retry beats late-night message for HDFC cards"
- At case ~280: "Bandit learned: 8% off > 12% off for cart values ₹1,000-1,500"
- At case ~420: "Bandit learned: promise-to-pay replies deserve 5-day pause, not immediate follow-up"
- At case ~600: "Federated priors from other Zenith-vertical merchants imported"

## Underlying data (for building the chart)

Sampled at every 50 cases:

| Cases seen | LLM-only rate | Bandit+LLM rate |
|---|---|---|
| 0 | 22.0% | 20.0% |
| 50 | 21.8% | 19.5% |
| 100 | 22.1% | 20.8% |
| 150 | 22.0% | 22.4% |
| 200 | 21.9% | 24.6% |
| 250 | 22.2% | 27.3% |
| 300 | 22.0% | 29.8% |
| 400 | 21.8% | 32.7% |
| 500 | 22.1% | 34.9% |
| 600 | 22.0% | 36.1% |
| 700 | 21.9% | 37.0% |
| 800 | 22.0% | 37.8% |
| 900 | 22.1% | 38.0% |
| 1000 | 22.0% | 38.2% |

**Final gap:** +16.2 percentage points, ~74% relative improvement.

## Video beat

**Duration:** 25 seconds
**Screen composition:** full-screen chart

- **[0:00]** Chart appears empty with axes labeled
- **[0:02]** Grey LLM-only line draws left-to-right, flat
- **[0:06]** Green Bandit+LLM line starts drawing, initially below grey
- **[0:10]** Green line crosses grey at ~case 200 (moment emphasized with a subtle chime)
- **[0:12-0:22]** Green line climbs; annotation callouts pop in one at a time as the line reaches each milestone
- **[0:23]** Chart complete; big number appears: "**+16.2 pp** — bandit outperforms LLM-only after ~200 cases"

**Voiceover:**
> *"Here's the difference. Grey line: an LLM picks the action every time. Never learns. Flat at 22%. Green line: our contextual bandit. Explores for the first 200 cases, then discovers what actually works — and climbs to 38%. Every merchant. Every playbook. Sharper every day."*

## Simulator seed
```yaml
batch_simulation:
  total_cases: 1000
  duration_days: 30
  merchants: [kajal_and_co, zenith_learning, sharma_distributors]
  playbook_distribution:
    failed_payment: 40%
    checkout_abandonment: 30%
    subscription_failure: 22%
    b2b_overdue: 8%
  
  arms_true_reward_by_context:
    # Ground truth for validating bandit convergence
    hdfc_credit_saturday_night:
      silent_retry_monday: 0.78
      whatsapp_now: 0.09
      immediate_retry: 0.34
    ...
```

---

# System Beat B2 — The Uplift ROI Panel

**Star of the show:** Honest incremental attribution
**Duration in video:** ~20 seconds

## What we show

Full-screen dashboard panel titled "Recovery ROI — Q3 2026 (simulated)"

Two big numbers side-by-side:

**LEFT (grey/muted, smaller):**
- **Gross recovery: ₹14,80,000**
- 35.2% of ₹42,00,000 at risk
- Subtitle: "The number most systems report"

**RIGHT (green, larger, emphasized):**
- **Incremental recovery: ₹9,20,000**
- 62% of gross was truly caused by us
- Subtitle: "The number that's actually true"

Below, a small four-cell grid showing the uplift buckets:

| Bucket | Cases | Amount | Our verdict |
|---|---|---|---|
| Persuadables (we intervened, we caused the recovery) | 6,240 | ₹9,20,000 | ✅ True win |
| Sure things (would have paid anyway) | 3,180 | ₹5,60,000 | ⚠️ Would happen without us |
| Lost causes (won't pay regardless) | 1,890 | ₹4,20,000 | ⏸️ Correctly skipped intervention |
| Do-not-disturbs (intervention would HURT) | 690 | ₹1,80,000 | 🛑 Correctly skipped intervention |

Bottom small text: "Holdout methodology: 5% of eligible cases receive no intervention. Uplift estimated as CATE across matched context buckets. Confidence interval ± 4.1%."

## Video beat

**Duration:** 20 seconds
**Screen composition:** full-screen ROI panel

- **[0:00]** Panel loads. Both numbers grey initially.
- **[0:03]** Left number brightens: "Gross recovery ₹14,80,000, 35.2%"
- **[0:07]** Right number brightens with a shimmer: "Incremental recovery ₹9,20,000, 62% true attribution"
- **[0:11]** Four-cell grid appears below, filling in bucket-by-bucket
- **[0:15]** Highlight animation on the "Sure things" cell: "₹5.6L would have come back without us. We don't take credit."
- **[0:18]** Highlight on "DNDs": "For 690 cases, our intervention would have HURT. We skipped."

**Voiceover:**
> *"Every recovery system reports the ₹14.8 lakhs. But how much did the system actually cause? Our uplift model uses a small holdout group to answer honestly: ₹9.2 lakhs incremental. ₹5.6 lakhs would have come back on its own. And for 690 customers, an intervention would have annoyed them into cancelling — so we didn't send it. This is honest ROI."*

---

# System Beat B3 — The Federated Downtime Save

**Star of the show:** Cross-merchant intelligence detects a bank outage and pauses retries platform-wide
**Duration in video:** ~25 seconds

## What we show

Network Intelligence panel, real-time timeline.

## Timeline (simulated, plays live in demo)

### t=0 — SBI UPI success rate stable at 82%

Network dashboard shows healthy heatmap. All banks green.

### t=+0:00 to t=+1:30 — SBI UPI success rate drops sharply

Across 8 different merchants (Kajal & Co., Zenith Learning, Sharma Distributors, and 5 others in the simulator), SBI UPI success rate drops from 82% to 41% in 90 seconds. This is not local to any single merchant — it's a network-wide degradation.

Individual merchants can't see this. Recover's federated layer can.

### t=+1:30 — Network anomaly detector fires

```json
{
  "alert_id": "alert_20260910_143203_sbi_upi",
  "alert_type": "bank_method_degradation",
  "detected_at": "2026-09-10T14:32:03+05:30",
  "affected_bank": "SBI",
  "affected_method": "upi",
  "severity": "high",
  "z_score": -3.7,
  "sample_size": 340,
  "affected_merchants_count": 8,
  "network_wide_success_rate_last_10min": 0.41,
  "baseline_rate": 0.82,
  "recommended_action": "pause_sbi_upi_retries_platform_wide_for_30_min"
}
```

### t=+1:31 — Auto-response fires across all merchants

- All bandits platform-wide receive updated priors: `SBI UPI now = degraded, prefer alternate methods`
- Any scheduled retries against SBI UPI in the next 30 minutes are held
- New failed payments that would have retried SBI UPI now bandit-pick "switch to card/net-banking + payment link"

### t=+30 min — Auto-recovery check

Network detector re-checks: SBI UPI success rate now back to 78%. Alert marked as `resolved`. Auto-pause lifted. Priors return to baseline.

## Dashboard state

The Network Intelligence panel shows:
- Live heatmap with the SBI × UPI cell flashing red
- Alert banner: **⚠️ Network alert: SBI UPI degradation detected 14:32 IST — auto-pausing SBI UPI retries platform-wide**
- Impact counter (live-updating):
  - `Cases affected: 340`
  - `Retries auto-paused: 340`
  - `Switched to alternate method: 187`
  - `Estimated cases saved from cascading failure: ~260`
- Bank comparison: HDFC UPI (green, 84%), ICICI UPI (green, 79%), SBI UPI (red, 41%), Axis UPI (green, 81%)

## Video beat

**Duration:** 25 seconds
**Screen composition:** Network Intelligence panel, full-screen

- **[0:00]** Network heatmap steady, all cells green
- **[0:03]** SBI UPI cell begins pulsing amber
- **[0:06]** Amber intensifies; timeline ticker on the side shows: "SBI UPI: 82% → 71% → 58% → 41%"
- **[0:09]** Alert banner slams in: **"⚠️ Network alert: SBI UPI degradation detected"**
- **[0:12]** Text below animates: "Auto-pausing SBI UPI retries across 8 merchants — switching bandit priors to alternates"
- **[0:15]** Live counter starts ticking up: `Cases affected: 12... 47... 128... 340`
- **[0:19]** Split display: `Switched to card/net-banking: 187 successful | Retries into broken SBI UPI: 0`
- **[0:22]** Big text overlay: "Detection to platform-wide response: **91 seconds**"
- **[0:24]** Voiceover close, transitions to next beat

**Voiceover:**
> *"14:32 — SBI's UPI starts breaking. No individual merchant sees this. But we watch every Razorpay merchant, together. 91 seconds after the first signal, our network detected the pattern, paused SBI UPI retries platform-wide, and switched every affected bandit to alternate methods. 260 payments saved from a cascading failure. This is what only Razorpay can build."*

---

# Batch Results — The Closing Shot

**Duration:** ~20 seconds
**Screen composition:** dashboard "Q3 2026 Summary" screen

## Numbers on screen

```
────────────────────────────────────────────────
  Q3 2026 SIMULATION RESULTS
  1,000 cases · 30 days · 3 merchants · 4 playbooks
────────────────────────────────────────────────

  REVENUE
  At risk:            ₹42,00,000
  Gross recovered:    ₹14,80,000   (35.2%)
  Incremental:        ₹ 9,20,000   (62% true)
  Cost of recovery:   ₹    3,864   (₹0.42 / ₹100 recovered)

  ML PERFORMANCE
  Bandit convergence:      ~250 cases per playbook
  Bandit lift over LLM-only: +16.2 percentage points
  Uplift model accuracy:    ± 4.1% CI

  COMPLIANCE
  RBI violations:                    0
  TRAI violations:                   0
  Opt-outs honored:                  100% (avg 6.2s response)
  Human handoffs:                    23 (all with full context)

  NETWORK INTELLIGENCE
  Downtime alerts fired:             3
  Retries saved from broken rails:   ~700
  Federated updates propagated:      12,847

  AUDIT
  Every decision:            traceable ✅
  Every LLM output:          logged ✅
  Every bandit alternative:  captured ✅
  Every guardrail check:     recorded ✅
────────────────────────────────────────────────
```

**Voiceover:**
> *"One thousand cases. Thirty days. Three merchants. Four playbooks. ₹9.2 lakhs truly recovered. Zero compliance violations. Every decision auditable. This is Recover."*

---

# Simulator Requirements Summary

For all 9 beats to run cleanly, the simulator must support:

1. **Event stream generation** with all four event types on realistic time distributions
2. **Ground-truth counterfactuals** — each simulated customer has a `true_willingness_to_pay` known only to the simulator, used for validating uplift measurements
3. **Bank/method state simulation** with scheduled downtime events (for B3)
4. **Reply generation** with authentic Hinglish/multilingual patterns and known intent labels
5. **Time controller** — real-time mode for live demo of individual scenarios, fast-forward mode (~1 hour of sim time = 1 second of wall clock) for batch results
6. **Merchant seeding** — 3 merchants with distinct playbooks, thresholds, and volume characteristics
7. **Customer seeding** — the 6 persona customers pre-loaded, plus ~500 synthetic customers for the batch simulation
8. **Network state feed** — cross-merchant aggregations updating in real-time for the federated intelligence view

---

# Video Assembly

Final cut order and durations:

| Segment | Duration | Cumulative |
|---|---|---|
| Hook | 0:20 | 0:20 |
| Pitch reveal | 0:25 | 0:45 |
| S1 Suresh | 0:18 | 1:03 |
| S2 Priya | 0:16 | 1:19 |
| S3 Aditya | 0:15 | 1:34 |
| S4 Meera | 0:22 | 1:56 |
| S5 Vikram | 0:14 | 2:10 |
| S6 Sana | 0:10 | 2:20 |
| B1 Bandit curve | 0:25 | 2:45 |
| B2 Uplift ROI | 0:20 | 3:05 |
| B3 Federated downtime | 0:25 | 3:30 |
| Batch results | 0:20 | 3:50 |
| Close | 0:20 | 4:10 |

**Total: 4 minutes 10 seconds.** Fits comfortably in a 4-5 minute video budget with room for pacing pauses and title cards.

---

# Next steps

Once this file is signed off:

1. **Simulator scaffolding** — build the event generator, response simulator, and reply generator matching the schemas above.
2. **Agent core stubs** — get the 9-step loop wired end-to-end with mock LLM/bandit responses matching the JSON here.
3. **First playbook end-to-end** — pick Subscription (S1, S5) as the deepest, get it fully working with real LLM calls and bandit updates.
4. **Repeat for other playbooks** — Checkout (S2), Failed Payment (S3, S6), B2B (S4).
5. **System beats** — instrument the bandit curve data collection, uplift measurement, and federated anomaly detector.
6. **Dashboard** — build the merchant screens to render every state described above.
7. **Video capture** — run each scenario live with screen recording, then edit to the cuts above.
