# Recover — AI Revenue Recovery Agent for Razorpay

> Razorpay Buildathon: Track 03 — AI Revenue Recovery
> One-line pitch: **An AI agent that lives on the Razorpay dashboard, watches every merchant's revenue leaks in real time, diagnoses why money is slipping using a causal graph, picks the right action with a contextual bandit that learns across Razorpay's entire network, respects when *not* to intervene, listens to customer replies in Hinglish, and stops when it should.**

---

## 1. Vision & Positioning

### Why Razorpay should build this (not any random SaaS)

Individual merchants see their own trickle of failures — 100 declines a day, a handful of dropped carts, a few overdue invoices. They can't build real intelligence from that. **Razorpay sees the whole river**: millions of events across every bank, BIN, method, PSP, and hour of day, across every vertical. That cross-merchant view is a moat only Razorpay has.

"Recover" is the productized version of that moat. It's an agent that Razorpay merchants toggle on from their dashboard, and instantly get access to:

- **Federated network intelligence** — a shared learning layer that every merchant contributes to and benefits from, without leaking any merchant's data. Priors, downtime detection, and best-action patterns are learned across the entire Razorpay network.
- **Rail-native execution** — the agent doesn't just *tell* the merchant what to do. It executes through the same Razorpay rails already integrated: Payment Gateway retries, Subscriptions mandate re-registration, Payment Links, RazorpayX invoice reminders, Smart Collect, WhatsApp Business, SMS, email.
- **Compliance built in** — RBI mandate retry rules, TRAI messaging frequency, DPDP data handling — enforced by the platform, not left to the merchant.
- **Restraint as a feature** — the agent uses uplift modeling to skip intervention when the customer would have paid anyway. It honors opt-outs. It escalates hardship signals to humans. Trust is the moat inside the moat.

### The actor model

- **Merchant** — the buyer. Sees a dashboard, toggles playbooks on/off, sets guardrails, watches ₹ recovered.
- **Customer** — the person being recovered from. Experiences a well-timed, respectful, contextual nudge — not spam.
- **Razorpay** — the platform. Hosts the agent, provides the rails, enforces compliance, learns across the network.

---

## 2. Product Overview

**Recover** is a merchant-side product with four surfaces:

1. **Recovery Dashboard** — real-time view of revenue at risk, revenue recovered, incremental recovery (uplift-adjusted), active recoveries in flight, audit trail, ROI.
2. **Playbook Console** — merchant configures which recovery playbooks are on, sets caps (max attempts, discount limits, escalation triggers).
3. **Network Intelligence Panel** — the Razorpay-only view showing population-level bank health, current downtime alerts, learned action patterns, and merchant-vs-benchmark comparisons.
4. **Customer-facing touchpoints** — WhatsApp / SMS / email / one-click payment links / retry flows. These are what the end customer actually experiences, and where they reply back.

Behind these surfaces is the **Recovery Agent Core** — a shared Detect → Diagnose → Uplift-check → Decide → Guardrail → Execute → Listen → Learn → Audit loop that runs four **playbooks**, one per revenue-leak surface, all sharing a federated intelligence layer above them.

---

## 3. The Four Recovery Surfaces

All four share the same agent core; each has a specialized playbook (features, action space, stopping rules). Bandits, uplift models, and causal graphs are per-playbook (each has its own action space and outcome definition).

### 3.1 Failed one-time payments (D2C / e-commerce)
**Trigger:** `payment.failed` webhook.
**Signal:** Card declined, UPI timeout, bank downtime, insufficient funds, 3DS drop.
**Diagnosis features:** issuer bank, BIN, method, time-of-day, failure code, historical success rate for this (bank × method × hour) combo, customer's past payment methods, current network health for this bank.
**Action space (bandit arms):** retry now / retry at optimal hour / send payment link via alternate method / send WhatsApp nudge with saved cart / do nothing (respect low uplift).
**Stopping rules:** max 2 auto-retries, no messages after 9pm local, no more than 2 outreach attempts per 24h.

### 3.2 Checkout abandonment (D2C)
**Trigger:** `checkout.abandoned` event.
**Signal:** dropped at method selection / dropped at OTP / dropped at 3DS / dropped at price shock.
**Diagnosis features:** cart value, drop-off stage, customer segment (new vs returning), whether they've completed a purchase before, price-sensitivity signals from behavior.
**Action space (bandit arms):** WhatsApp with saved cart link / discount code (bounded, ladder of magnitudes) / suggest alternate payment method / do nothing.
**Stopping rules:** max 1 discount offer per customer per 30 days, max 3 abandonment nudges per customer per month.

### 3.3 Subscription / mandate failures (SaaS, edtech, OTT, D2C subs)
**Trigger:** `subscription.charged.failed` webhook.
**Signal:** UPI Autopay failure, eNACH mandate failure, card expired, mandate revoked, insufficient balance.
**Diagnosis features:** mandate history, historical failure dates (salary cycle inference), competing EMI dates for this customer's payment instrument, customer LTV, months on subscription, past recovery success.
**Action space (bandit arms):** retry on inferred salary date / dunning email sequence / WhatsApp with one-click Payment Link / mandate re-registration flow / pause with win-back / human handoff.
**Stopping rules:** RBI-compliant retry cap (max 3 retries per NACH mandate cycle), 24h between retries, hard stop after 15 days.

### 3.4 B2B overdue invoices (RazorpayX / Payment Links / Smart Collect)
**Trigger:** invoice due date passed without payment.
**Signal:** overdue by 1 / 7 / 15 / 30 days.
**Diagnosis features:** customer's past payment behavior (always late? first-time late?), invoice size, relationship tenure, promise-to-pay history, industry norms for this vertical.
**Action space (bandit arms):** polite reminder / firm reminder / offer partial payment / offer payment plan / accept promise-to-pay with follow-up / escalate to AR human / stop and mark for legal.
**Stopping rules:** max 1 email + 1 WhatsApp per week, escalation to human after 3 unacknowledged nudges, no messaging after promise-to-pay until promise date.

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│           CROSS-MERCHANT FEDERATED INTELLIGENCE LAYER                │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ Bank/PSP health  │  │ Population       │  │ Downtime detector │  │
│  │ heatmap (live)   │  │ priors for       │  │ (real-time        │  │
│  │                  │  │ bandit warm-start│  │ anomaly detection)│  │
│  └──────────────────┘  └──────────────────┘  └───────────────────┘  │
│  Only aggregated stats leave the merchant boundary. Privacy-safe.    │
└─────────────────────────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼───────────────────────────────┐
│                    RAZORPAY EVENT STREAM (simulated)                │
│  payment.failed | checkout.abandoned | subscription.charged.failed  │
│                  invoice.overdue | customer.replied                 │
└────────────────────────────────────┬───────────────────────────────┘
                                     │
                            ┌────────▼─────────┐
                            │  Event Ingestor  │
                            └────────┬─────────┘
                                     │
                            ┌────────▼─────────┐
                            │  Enrichment      │  (customer profile, LTV,
                            │  Layer           │   BIN data, historical
                            │                  │   stats, network priors)
                            └────────┬─────────┘
                                     │
              ┌──────────────────────▼──────────────────────┐
              │            RECOVERY AGENT CORE               │
              │                                              │
              │  1. DETECT ─────► route to playbook          │
              │                                              │
              │  2. DIAGNOSE ───► Causal DAG traversal       │
              │                   + LLM evidence extraction  │
              │                                              │
              │  3. UPLIFT ─────► "is this customer a        │
              │     CHECK         persuadable, or would      │
              │                   they have paid anyway?"    │
              │                   (skip if low uplift)       │
              │                                              │
              │  4. DECIDE ─────► Contextual Bandit picks    │
              │                   arm from action space      │
              │                   (LLM for edge cases only)  │
              │                                              │
              │  5. GUARDRAIL ──► Compliance checks (RBI/    │
              │                   TRAI/consent/caps)         │
              │                                              │
              │  6. EXECUTE ────► Deterministic Razorpay     │
              │                   API adapters               │
              │                                              │
              │  7. LISTEN ─────► LLM classifies inbound     │
              │                   customer replies (Hinglish,│
              │                   hardship, promise-to-pay)  │
              │                                              │
              │  8. LEARN ──────► Bandit updates from reward │
              │                   Causal DAG refines priors  │
              │                   Federated layer aggregates │
              │                                              │
              │  9. AUDIT ──────► Every step logged with     │
              │                   reasoning, alternatives    │
              │                   considered, and outcome    │
              └──────────────────────┬──────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
┌───────▼────────┐         ┌─────────▼────────┐        ┌──────────▼──────────┐
│ Execution      │         │ Merchant         │        │ Customer            │
│ Adapters       │         │ Dashboard        │        │ Touchpoints         │
│ - Retry API    │         │ - Overview       │        │ - WhatsApp (2-way)  │
│ - Payment Link │         │ - Playbooks      │        │ - SMS               │
│ - WhatsApp     │         │ - Bandit curves  │        │ - Email             │
│ - Email/SMS    │         │ - Uplift ROI     │        │ - Payment Link page │
│ - Mandate re-  │         │ - Network intel  │        │                     │
│   registration │         │ - Reply feed     │        │                     │
│                │         │ - Audit log      │        │                     │
└────────────────┘         └──────────────────┘        └─────────────────────┘
```

**Key architectural principle:** the agent core loop is shared across all four playbooks; the federated intelligence layer wraps around all of them. This is what makes both "cover all four surfaces" *and* "add real ML" tractable in hackathon time.

---

## 5. The Agent Loop in Detail

### Step 1 — Detect
- Webhook lands, event is normalized to a `RecoveryCase` object.
- Case is routed to the correct playbook based on event type.
- Dedup: if a case for this customer/entity is already in-flight, merge rather than duplicate.

### Step 2 — Diagnose (Causal DAG + LLM)
- Enrichment layer fetches: customer profile, past payment history, BIN metadata, current network health for this bank/method, method-level success rates.
- **Causal DAG traversal:** walks the failure-causes DAG for this playbook, computes posterior probability over root causes given observed features. This is structured Bayesian reasoning, not black-box guessing.
- **LLM evidence extraction:** the LLM annotates the case with structured evidence — pattern-matched signals from history ("3 consecutive failures on the 1st"), context ("high-LTV customer"), competing explanations to consider.
- Output is a diagnosis object:
  ```json
  {
    "root_cause": "salary_cycle_mismatch",
    "posterior_probability": 0.82,
    "causal_path": ["payment.failed", "insufficient_balance", "salary_cycle_mismatch"],
    "supporting_evidence": ["failed on 1st for 3 months", "paid on 7th once"],
    "alternative_hypotheses": [
      {"cause": "mandate_revoked", "probability": 0.09},
      {"cause": "account_closed", "probability": 0.04}
    ],
    "risk_factors": ["high LTV, avoid aggressive tone"]
  }
  ```

### Step 3 — Uplift Check (the "would they have paid anyway?" gate)
- Before spending any effort, ask: **is this case a persuadable, a sure thing, a lost cause, or a do-not-disturb?**
- The uplift model, trained on the small holdout group's counterfactuals, estimates the causal treatment effect for this case.
- If estimated uplift is below threshold → **skip intervention, mark as monitored, log the decision.** This saves cost, protects the customer's inbox, and gives honest incremental ROI numbers.
- ~5% of eligible cases go into the ongoing holdout (no intervention, tracked for outcome) to keep the uplift model learning.

### Step 4 — Decide (Contextual Bandit + LLM for edge cases)
- **Primary path — Contextual Bandit:** given the case's context vector (bank, method, hour, customer features, cart value, LTV, etc.), the bandit picks an arm from the playbook's action space using Thompson sampling (or LinUCB).
- The bandit's choice comes with a confidence and an exploration flag: is this exploit (best-known arm) or explore (deliberate sampling to learn)?
- **LLM edge-case path:** for cases the bandit flags low-confidence, or that hit unusual feature combinations, an LLM decision call reviews and can override with reasoning.
- **LLM always handles message generation:** even when the bandit picks "send WhatsApp Payment Link," the LLM writes the message — tone-adapted, Hinglish-aware, personalized to the case using approved DLT template scaffolds.
- Output:
  ```json
  {
    "chosen_arm": "whatsapp_payment_link",
    "arm_confidence": 0.71,
    "mode": "exploit",
    "expected_recovery_probability": 0.68,
    "alternative_arms_considered": [
      {"arm": "retry_at_9am", "expected_reward": 0.61},
      {"arm": "email_only", "expected_reward": 0.42}
    ],
    "message_generation": {"tone": "friendly_hinglish", "template_id": "sub_recovery_v3"},
    "reasoning": "Bandit prefers WhatsApp+link for this (bank, hour, LTV) context. Retry alone had 0.61 in similar past cases; WhatsApp lifts to 0.68."
  }
  ```

### Step 5 — Guardrail Check (deterministic, non-LLM)
- RBI: retry count within mandate cycle limits? Time since last retry ≥ 24h?
- TRAI: message count in last 24h ≤ merchant cap? Not sending between 9pm–9am?
- Merchant caps: within discount budget? Within escalation policy?
- Consent: customer has WhatsApp opt-in? Not opted out of marketing?
- Network status: bank/PSP is not currently in a detected downtime state (don't retry into a broken rail).
- If any check fails → downgrade to next-best action or stop.

### Step 6 — Execute
- Deterministic adapters call the actual Razorpay APIs (or simulated APIs in the demo).
- Every execution attempt gets a request ID and idempotency key.

### Step 7 — Listen (Inbound Reply Intelligence)
- When a customer replies to WhatsApp / SMS / email, the reply is captured.
- **LLM classifies the reply** — multilingual, code-mixed (Hinglish, Tamglish, Benglish), including emojis and voice notes (transcribed):
  ```json
  {
    "language": "hinglish",
    "intent": "promise_to_pay",
    "sentiment": "cooperative",
    "extracted_entities": {"promise_date": "2026-09-05", "amount": "full"},
    "hardship_signal": false,
    "opt_out_signal": false,
    "recommended_state_update": "PAUSE until 2026-09-05, then reactivate"
  }
  ```
- Case state updates: promise-to-pay is tracked, hardship escalates to human, opt-out is honored forever.

### Step 8 — Learn
- **Bandit reward update:** the outcome (recovered? amount? time-to-pay?) becomes the reward signal. Bandit updates its arm-value posteriors for this context.
- **Causal DAG refinement:** posterior probabilities on the DAG's edges are updated with the observed outcome.
- **Federated aggregation:** anonymized (bank, method, hour, arm, outcome) tuples flow to the network layer, updating population priors that seed *every* merchant's bandit.
- **Uplift model retraining:** periodic retraining as the holdout group accumulates counterfactuals.

### Step 9 — Audit
- Full record: event → diagnosis (causal path + LLM evidence) → uplift decision (with counterfactual estimate) → bandit choice (with alternatives considered) → guardrail results → execution attempt → customer reply (if any) with classification → outcome → learning updates.
- Every action is queryable. Every "we didn't act" decision has a reason.
- **This audit trail is the killer feature for regulators and risk teams. It must be prominently visible in the demo.**

---

## 6. The AI/ML Stack (what makes this different)

This is the section that separates "Recover" from "we built an LLM wrapper." We use the right tool for each sub-problem.

### 6.1 The Large Language Model (Claude / GPT)
**Used for:** evidence extraction during diagnosis, message generation (Hinglish/tone-adaptive), inbound reply classification, edge-case decision override.
**Not used for:** the actual action selection, compliance checks, API execution, money movement, learning from outcomes.
**Why:** LLMs are best at unstructured language tasks and reasoning over messy context. They are the wrong tool for decisions that need to *learn from outcomes over time* — that's what bandits are for.

### 6.2 Contextual Bandit (Thompson Sampling / LinUCB)
**Used for:** action selection within each playbook's bounded action space.
**Why:** every recovery attempt gives us a labeled outcome (recovered = 1, not = 0, weighted by ₹). This is exactly the shape of a contextual bandit problem, and it's the *right* algorithm for online personalization under uncertainty. Ad-tech, recommendation systems, Doordash's routing — all use this pattern.
**Learning:** each case updates the arm posteriors. Over 500-1000 cases per playbook, the bandit learns bank-hour-segment specific policies that no human would have written down.
**Exploration:** Thompson sampling naturally balances exploit vs. explore. Every choice is logged with its mode (exploit / explore) for the audit trail.
**Cold-start:** federated network priors warm-start every merchant's bandit — day-one intelligence, not weeks of learning.

### 6.3 Uplift Modeling (Causal Treatment Effect)
**Used for:** deciding *whether* to intervene at all, and for reporting honest ROI.
**Why:** the naive metric — "% of cases where we sent an outreach and got paid" — is misleading. Many of those customers would have paid without any nudge. Uplift modeling separates the four segments (persuadable / sure thing / lost cause / do-not-disturb) using a small holdout group as ground truth.
**How:** for ~5% of eligible cases we do nothing, tracking outcomes. Comparing intervened vs. holdout within similar-context buckets gives conditional average treatment effect (CATE) estimates. We only intervene when estimated uplift × recovery amount exceeds cost of intervention.
**The killer metric:** "Incremental Recovery Rate" — recovery attributable to the agent's actions, not correlated with them. This is what a real Razorpay finance team would want to see.

### 6.4 Causal DAG for Diagnosis
**Used for:** root-cause classification with interpretable causal paths.
**Why:** instead of asking an LLM "why did this fail" and trusting the answer, we build a directed acyclic graph of failure causes per playbook. Bayesian inference over the DAG gives posterior probabilities that are traceable and auditable.
**How:** the DAG is small (10-20 nodes per playbook) and hand-encoded from Razorpay's known failure taxonomy. Priors come from historical stats. Case-specific features update posteriors via standard Bayesian updating.
**Interpretability:** every diagnosis has a *path* through the DAG. The audit trail shows the walk. Auditors can literally see the reasoning.

### 6.5 Federated Cross-Merchant Intelligence
**Used for:** network-wide bank/PSP health monitoring, real-time downtime detection, population priors that seed every merchant's bandit.
**Why this is Razorpay's actual moat:** no individual merchant sees enough data to learn robust patterns. The Razorpay network sees ~10 million events per day. Aggregated statistics (never individual merchant data) become a shared asset.
**Privacy safety:** only aggregated statistics leave the merchant boundary (e.g., "success rate for HDFC credit card in hour 14 across merchants of size class M is 0.67 ± 0.03"). No customer-level or merchant-level data crosses lines.
**Real-time downtime detection:** anomaly detection on time-series aggregates — when 8+ merchants see SBI UPI success drop 40% in 10 minutes, the network flags it and pauses UPI retries platform-wide, avoiding a stampede into a broken rail.

### 6.6 Inbound Reply Intelligence (LLM again, but critical)
**Used for:** classifying customer replies to WhatsApp / SMS / email in Hinglish, Tamglish, Benglish, code-mixed English, emojis, and transcribed voice notes.
**Why this earns the LLM its keep:** the surface area of human replies is infinite. Rules can't capture "bro paisa nahi hai abhi, next month kar dunga" as a promise-to-pay, or "papa ki tabiyat kharab hai" as a hardship signal. An LLM does this in real-time with structured output.
**What it enables:** promise-to-pay tracking, hardship escalation to humans, respectful pause on soft "kal try karta hoon" replies, immediate honor of explicit STOP requests.

---

## 6.7 What makes Recover different from the baseline

**The baseline that every other team will build:**
- Webhook comes in → Claude/GPT prompted with the case → LLM outputs an action → code executes it → done.

**What we build:**

| Layer | Baseline (what everyone else does) | Recover (what we do) |
|---|---|---|
| Diagnosis | "LLM, why did this fail?" | Causal DAG with posterior probabilities + LLM evidence extraction — interpretable and auditable |
| Action selection | "LLM, what should we do?" | Contextual bandit learning from outcomes; LLM only for edge cases |
| Metric | Gross recovery rate | Incremental recovery rate (uplift-adjusted) — honest causal attribution |
| Intervention gating | Always try if allowed | Uplift check first — skip when customer would have paid anyway |
| Learning | None between cases | Bandit updates every case; DAG priors refine; network-wide propagation |
| Cross-merchant | Impossible | Federated intelligence with real-time downtime detection |
| Inbound replies | Ignored or human-routed | LLM classifies Hinglish/hardship/promise-to-pay, updates state autonomously |
| Message generation | Static templates | LLM-generated, tone-adaptive, code-mixed language |
| Reasoning trace | LLM chain-of-thought (unstructured) | Structured causal path + bandit's considered alternatives + reward posterior |

**The one-liner for judges:** *"Everyone at this Buildathon can prompt an LLM. We built an ML system that learns, reasons causally, respects when not to act, and gets smarter across Razorpay's entire network."*

---

## 7. Compliance & Stopping Rules

This is where Recover separates from a toy demo. Every playbook has explicit, enforced rules:

### RBI (Reserve Bank of India)
- **NACH/eNACH mandates:** max retry attempts per cycle, minimum 24h between retries, presentation window respected.
- **Auto-debit consent:** mandate must be valid; agent triggers re-registration flow if expired/revoked.

### TRAI (Telecom Regulatory Authority of India)
- **SMS/WhatsApp:** DLT-registered templates only, no messaging 9pm–9am local, frequency caps.
- **Consent:** honor opt-outs immediately (LLM-classified STOP or "band karo" replies trigger permanent hold).

### DPDP (Digital Personal Data Protection Act)
- No PII in LLM prompts unnecessarily; customer IDs abstracted.
- Aggregated statistics only in the federated layer — no individual data crosses merchant boundaries.
- Data retention limits on audit logs.

### Merchant-configurable caps
- Max attempts per case.
- Max discount value.
- Max messages per customer per week.
- Human-escalation threshold.

### Hard stopping rules (agent will refuse to continue)
- Customer explicitly opts out (STOP, "band karo," "not interested").
- LLM classifies reply as hardship signal → pause and human handoff.
- Max attempts reached.
- Merchant pauses playbook.
- Network layer detects bank downtime → pause retries into that rail platform-wide.
- Uplift model estimates negative uplift for this case → skip.

### The holdout group (compliance angle)
The ~5% uplift holdout is fully compliant — these are cases where we simply *do nothing*, which is the safest possible default. No merchant needs to opt into it because doing nothing is never a violation. Merchants can see the aggregate holdout results in their dashboard to trust the uplift numbers.

---

## 8. Data Model

### Core tables (Postgres)

```
merchants
  id, name, vertical, playbook_config (jsonb), created_at

customers
  id, merchant_id, name, phone, email, ltv, tenure_days,
  consent (jsonb: whatsapp, sms, email, marketing, opted_out_at),
  metadata (jsonb: preferred_method, salary_cycle_inferred, etc.)

payment_methods
  id, customer_id, type (card/upi/nb), bin, bank, last_used_at, success_rate_90d

events
  id, merchant_id, customer_id, event_type, payload (jsonb),
  received_at, processed_at

recovery_cases
  id, merchant_id, customer_id, playbook, status (open/in_flight/recovered/stopped/failed/holdout),
  amount_at_risk, amount_recovered, opened_at, closed_at,
  diagnosis (jsonb), current_step,
  uplift_bucket (persuadable/sure_thing/lost_cause/dnd/unknown),
  is_holdout (boolean)

agent_decisions
  id, case_id, step_number, decision_source (bandit/llm/rule),
  bandit_context_vector (jsonb), bandit_chosen_arm, bandit_arm_confidence, bandit_mode (exploit/explore),
  llm_prompt_hash, llm_response (jsonb),
  causal_path (jsonb), diagnosis_posteriors (jsonb),
  chosen_action, action_params (jsonb), reasoning, uplift_estimate,
  guardrail_checks (jsonb), created_at

execution_attempts
  id, case_id, decision_id, action_type, adapter, request_payload (jsonb),
  response_payload (jsonb), status, idempotency_key, attempted_at

customer_replies
  id, case_id, channel (whatsapp/sms/email/voice), raw_text,
  llm_classification (jsonb: language, intent, sentiment, entities, hardship_signal, opt_out_signal),
  applied_state_update, received_at

audit_events
  id, case_id, actor (agent/human/system), event, details (jsonb), created_at

-- ML-specific tables --

bandit_arms
  playbook, arm_name, action_type, action_params_template (jsonb)

bandit_rewards
  id, case_id, decision_id, arm_name, context_vector (jsonb),
  reward_value, reward_type (recovered_amount/binary), observed_at

bandit_posteriors  -- for LinUCB: A matrix + b vector per arm; for Thompson: alpha/beta
  playbook, arm_name, context_bucket, alpha, beta, n_pulls, updated_at

uplift_holdouts
  case_id, assigned_at, holdout_reason, outcome (recovered/not),
  context_features (jsonb), used_in_training (boolean)

uplift_model_snapshots
  id, playbook, trained_at, model_type, feature_importances (jsonb),
  bucket_uplifts (jsonb)  -- CATE estimates per context bucket

causal_dag
  playbook, node_id, node_type (root_cause/observable/intervention),
  parents (jsonb), prior_probability, updated_at

causal_edge_updates
  playbook, from_node, to_node, observed_transitions, total_observations, updated_at

network_stats  -- federated intelligence, aggregated only
  bank, method, hour_of_day, day_of_week, merchant_size_class,
  success_rate, sample_size, updated_at

network_alerts  -- real-time downtime detections
  id, alert_type (downtime/degradation/anomaly),
  affected_bank, affected_method, severity,
  detected_at, resolved_at, affected_merchants_count
```

---

## 9. Demo Personas & Scenarios

Three merchants, six persona-driven scenarios plus three system-level demo beats. Each is a self-contained 20-45 second video segment.

### Merchants

**M1 — Kajal & Co.** (D2C beauty/personal care, Razorpay Payment Gateway)
- Vertical: Consumer / beauty & personal care
- Volume: ~3,000 orders/day
- Uses: failed payment recovery + checkout abandonment playbooks
- Why this vertical: highest cart abandonment rates in Indian e-commerce (60%+); visually rich for WhatsApp recovery (product images); very Razorpay-native customer base.

**M2 — Zenith Learning** (edtech, monthly course subscriptions via Razorpay Subscriptions + UPI Autopay)
- Vertical: Education / SaaS-subscription
- Volume: ~30,000 active subscribers (parents paying for their children)
- Uses: mandate failure recovery playbook (this is the deepest AI story)
- Why this vertical: bigger tickets (₹1,499-4,999/mo) than OTT, richer salary-cycle story (parents' salary cycles + competing home-loan EMIs), massive Razorpay segment (Unacademy/PhysicsWallah/Cuemath all use it).

**M3 — Sharma Distributors** (F&B/FMCG distribution to restaurants and kirana stores, RazorpayX + Payment Links + Smart Collect)
- Vertical: B2B / distribution
- Volume: ~500 invoices/month, average ticket ₹80k-2L
- Uses: overdue invoice chaser playbook
- Why this vertical: F&B distribution is the archetypal chronic-late-payer industry in India; RazorpayX-native customer profile; visually specific invoices land well on video.

### Persona-driven scenarios (one per video segment)

**S1 — Suresh (Zenith Learning)** — *the salary-mismatch save*
- Suresh is a parent, paying ₹2,999/month for his son's JEE coaching subscription.
- The UPI Autopay mandate has failed on the 1st for 3 consecutive months. His home-loan EMI also debits on the 1st.
- **Causal DAG diagnosis:** posterior 0.82 on "salary_cycle_mismatch competing with EMI"; posterior 0.09 on "mandate revoked"; posterior 0.04 on other causes.
- **Uplift check:** persuadable bucket (past behavior shows he wants to keep the subscription, just needs timing help).
- **Bandit decision:** arm = "retry_at_inferred_date + WhatsApp payment link fallback." Confidence 0.71. Alternatives considered: pure retry (0.61), dunning email only (0.34).
- **Outcome:** ✅ retry succeeds on the 7th. Full-year LTV preserved.
- **Demo beat:** show the causal DAG lighting up with the traversal path; show the bandit's arm choice with alternatives it considered.

**S2 — Priya (Kajal & Co.)** — *the cart abandonment recovery*
- Priya added ₹1,240 of skincare (serum + moisturizer + sunscreen) and dropped at price shock during checkout.
- **Diagnosis:** price-sensitive segment; first-time cart abandoner from this device; high intent (spent 4 min browsing).
- **Uplift check:** persuadable (returning visitor, high engagement).
- **Bandit decision:** arm = "WhatsApp saved cart + 8% off." Bandit has learned that for this (cart value × segment × time-of-day) context, 8% is the sweet spot — 5% is too little, 12% wastes margin.
- **Message (LLM-generated, Hinglish):** *"Hi Priya! Aapka cart wait kar raha hai 💕 Yeh raha aapka skincare set — plus flat 8% off, aaj tak. Complete karo →"*
- **Outcome:** ✅ recovered ₹1,141.
- **Demo beat:** show the actual WhatsApp message rendered; show the bandit's price-ladder learning curve.

**S3 — Aditya (Kajal & Co.)** — *the network intelligence timing save*
- Aditya's HDFC credit card failed at 11:34pm on a Saturday.
- **Diagnosis:** issuer transient failure. Not a customer-side issue.
- **Federated network signal:** the network layer confirms HDFC credit card success rate is currently 34% in this window, vs. 78% at 9am Monday. Network anomaly not detected — this is normal degradation, not downtime.
- **Uplift check:** sure-thing bucket if we retry at 9am (customer has always paid); persuadable if we message tonight (small lift, high cost).
- **Bandit decision:** arm = "silent retry at 9am Monday, no message." Bandit has learned that messaging tonight annoys this segment more than it recovers.
- **Outcome:** ✅ auto-recovered on Monday retry, zero messages sent, zero customer annoyance.
- **Demo beat:** show the network intelligence heatmap; show the bandit's decision to *not send a message* (restraint as intelligence).

**S4 — Meera (Sharma Distributors)** — *the B2B chase with partial payment*
- Meera is the AP clerk at a 30-restaurant chain. Her outstanding invoice: ₹1,45,000 for 60 crates of cooking oil, 12 days overdue.
- **Diagnosis:** chronic-late payer (always pays but often 15-25 days late), invoice size fits her chain's typical AP cycle.
- **Uplift check:** persuadable (unlike a delinquent, she's just slow — a nudge accelerates).
- **Bandit sequence:** polite reminder day 12 → firm reminder day 17 → partial-payment option day 20.
- **Customer reply (LLM-classified):** *"boss, 50% abhi kar deti hoon, baaki 25 tak"* → intent: promise_to_pay, entities: {partial: 50%, promise_date: 25th}.
- **Outcome:** ✅ ₹72,500 recovered immediately; remainder tracked with countdown; full amount recovered by day 25.
- **Demo beat:** show promise-to-pay tracker with countdown; show the LLM reply classification popup.

**S5 — Vikram (Zenith Learning)** — *the graceful human handoff*
- 18-month subscriber. Mandate failed. Bandit's first attempt: WhatsApp Payment Link.
- **Customer reply (LLM-classified):** *"bhaisaab beta ab coaching nahi le raha, cancel kar do please"* → intent: churn_confirmation, sentiment: neutral, hardship_signal: false.
- **Agent decision:** stop recovery, hand off to human retention team with full context, log as high-LTV churn.
- **Outcome:** ⏸️ no further recovery attempted; human retention team offers a course pause + resume offer; customer takes the pause.
- **Demo beat:** show the agent *choosing to stop* — the trust story. Show the human handoff card with full case history.

**S6 — Sana (Kajal & Co.)** — *the compliance guardrail*
- Payment failed, agent starts recovery sequence with a WhatsApp nudge.
- **Customer reply:** *"STOP"* (short and clear).
- **LLM classification:** intent: explicit_opt_out, hardship_signal: false, opt_out_signal: TRUE.
- **Agent decision:** hard stop within seconds. Consent revoked in DB. No further messages ever, across all playbooks.
- **Outcome:** ⛔ recovery abandoned; ₹0 recovered; compliance preserved; audit log shows the STOP was honored within 4 seconds.
- **Demo beat:** show the audit log timeline with STOP → CONSENT_REVOKED → HOLD_ALL_CHANNELS in real-time.

### System-level demo beats (dashboard shots)

**B1 — The Bandit Learning Curve**
- Chart: two lines over 1,000 simulated cases.
- Line 1 (baseline): "LLM-only policy" — flat ~22% recovery rate.
- Line 2 (Recover): "Bandit + LLM" — starts at ~20% (exploration), crosses over at case ~200, ends at ~38%.
- Small annotations: "bandit learned to skip evening messages for HDFC users," "discovered UPI switch works for card failures."
- **Video line:** *"The agent doesn't stay the same. Every case makes it sharper."*

**B2 — The Uplift ROI Panel**
- Two big numbers side by side.
- Left: "Gross recovery: ₹14,80,000 (35.2%)"
- Right, larger: "Incremental recovery: ₹9,20,000 (62% true attribution)"
- Small explainer: "Of the ₹14.8L recovered, ₹9.2L was caused by our interventions. ₹5.6L would have come back without us. We report only what we truly earned."
- **Video line:** *"Everyone measures recovery. We measure recovery we actually caused."*

**B3 — The Federated Downtime Save**
- Real-time simulated event: at t=0, SBI UPI success rate drops from 82% to 41% across 8 merchants.
- Network layer detects anomaly at t=90 seconds.
- Alert fires: "SBI UPI degradation detected, pausing retries platform-wide, switching bandit priors to prefer alternate methods for next 30 minutes."
- Dashboard shows: "Cases affected: 340. Actions taken: retried via UPI: 0. Switched to card/net-banking: 340. Estimated cases saved from stampede failure: 260."
- **Video line:** *"When SBI goes down at 3pm, our agent knows within 90 seconds — because we watch every Razorpay merchant, together. No merchant could see this alone."*

### The batch results screen (closing shot)

Run the agent against a simulated batch of 1,000 cases over 30 simulated days across the four surfaces. Show:
- ₹42,00,000 at risk → ₹14,80,000 gross recovered → **₹9,20,000 incremental (uplift-adjusted)**
- Recovery rate by playbook (subscription: 42%, checkout: 31%, failed payment: 38%, B2B: 28%)
- Compliance: 0 RBI violations, 0 TRAI violations, 100% opt-outs honored within 10 seconds
- Cost of recovery: ₹0.42 per ₹100 incremental recovered
- Bandit performance: converged in ~250 cases per playbook; outperformed LLM-only baseline by ~16 percentage points
- Every case has an audit trail one click away

---

## 10. Merchant Dashboard (what merchant sees)

### Home
- Live ticker: cases opened today, cases in flight, ₹ recovered today, ₹ incremental today, ₹ at risk right now.
- Recovery funnel: opened → diagnosed → uplift-checked → action taken → recovered / stopped.
- Playbook toggle row: 4 playbooks, on/off, cases active in each.
- Network intelligence banner: any active downtime alerts.

### Playbook detail
- Config: caps, guardrails, escalation rules, allowed action set.
- Performance: recovery rate, incremental recovery rate, avg time to recovery, cost per recovery.
- **Bandit learning curve:** small time-series chart showing this playbook's bandit converging.
- **Uplift buckets:** pie chart of persuadable / sure thing / lost cause / DND classifications this week.
- Recent cases: table with status, amount, current step, next action time.

### Case detail (the killer screen)
- Full timeline: event → diagnosis (with causal DAG visualization) → uplift decision → bandit choice (with alternatives) → guardrail checks → execution attempt(s) → customer replies (with LLM classifications) → outcome.
- **Causal DAG visualization:** interactive graph, nodes highlighted along the diagnosis path.
- **Bandit alternatives:** small ranked list of arms considered, with expected reward for each and why the chosen arm won.
- Customer profile with consent status and reply history.
- Manual override buttons (pause, escalate, stop).

### Network Intelligence (the Razorpay-only view)
- **Bank/method heatmap:** live, refreshed every 60 seconds — success rates by bank × method × hour, computed across all merchants.
- **Active alerts:** current downtime detections with affected merchants count.
- **Population priors panel:** "for merchants like you in your vertical, X action works Y% better than the network average."
- **Cross-merchant benchmark:** your recovery rate vs. vertical median vs. top-decile.

### Audit & compliance
- Filterable log: every decision, every action, every stop, every uplift skip.
- Compliance report: retry counts, message counts, opt-outs honored, average time to honor.
- Uplift transparency: holdout group size, aggregate outcomes, methodology explainer.

---

## 11. Data Simulator (realistic seeding)

**We cannot use real customer data. We build a simulator whose outputs are statistically indistinguishable from real Razorpay traffic, with the critical addition of ground-truth counterfactuals for uplift validation.**

### What we seed with real numbers
- Public bank/method success rate distributions.
- Public UPI PSP success rate splits.
- Real Indian salary date distribution (peak 1st, 7th, 10th) + competing EMI date distributions.
- Real Razorpay webhook payload schemas (from public docs).
- Real BIN → issuer → method mappings.
- Real DLT template structures for WhatsApp Business.
- Real Hinglish/Tamglish/Benglish reply patterns from public consumer research.

### What we synthesize
- Customer profiles across six personas + hundreds of variants.
- Time-distributed event stream: 1,000 events over 30 simulated days.
- Realistic failure code distributions per bank/method/hour.
- Realistic customer response patterns (some reply, some don't, some in Hinglish, some in English, some emoji-only).

### Simulator components
1. **Event generator** — produces realistic webhook payloads on a schedule.
2. **Customer response simulator** — models whether a customer clicks a payment link, replies to WhatsApp, pays on retry. **Critically, each simulated customer has a "true willingness to pay" attribute that only the simulator knows** — this is our ground-truth counterfactual for uplift validation.
3. **Bank/method state simulator** — some banks "have downtime" for windows; success rates vary by hour; scheduled downtime events feed the federated detection demo (B3).
4. **Reply generator** — produces realistic Hinglish/multilingual customer replies for the LLM classifier to consume, with known intent labels for validation.
5. **Time controller** — real-time (for live demo) or fast-forward (30 days in 90 seconds for the batch results and bandit convergence shots).

**In the video, we say honestly:** *"Recover is running against a simulated event stream seeded with public Razorpay benchmark data and realistic Indian payment patterns. In production, it plugs into the real Razorpay webhook stream unchanged. Our uplift measurements are validated against known counterfactuals in simulation."*

---

## 12. Tech Stack

### Frontend
- **Next.js 14+** (App Router, TypeScript)
- **Tailwind CSS** + shadcn/ui for merchant dashboard
- **Recharts** for analytics
- **React Query** for data fetching
- **React Flow** or **D3** for causal DAG visualization

### Backend
- **Python (FastAPI)** — recommended for the agent core, because both the LLM tooling and the ML tooling (bandits, uplift, causal inference) are mature and painless in Python.

### Data
- **Postgres** (main store — including bandit posteriors as jsonb)
- **Redis** (event queue, dedup, rate limiting, real-time network alert broadcasting)

### AI / ML
- **Anthropic Claude Sonnet 4.6** via API — for diagnosis evidence extraction, message generation, inbound reply classification.
- **Contextual bandits:** hand-rolled Thompson sampling (~200 lines) or `vowpalwabbit` Python bindings for LinUCB. Simple libraries are fine here — the algorithm is well-understood.
- **Uplift modeling:** `causalml` or `econml` (from Microsoft) — proven, well-documented libraries. Or a hand-rolled T-learner if we want to keep dependencies light.
- **Causal DAG:** hand-encoded per playbook (~20 nodes each) with a small Bayesian updater; `pgmpy` or `pomegranate` if we want a library, but hand-rolled is fine.
- **Federated intelligence:** just SQL aggregations + a time-series anomaly detector (z-score over rolling window is enough for the demo).

### Integrations (simulated in demo, real API-shaped)
- Razorpay Payment Gateway API (retries, payment links)
- Razorpay Subscriptions API (mandate management)
- Razorpay Payment Links API
- RazorpayX API (invoicing)
- WhatsApp Business API (DLT templates, 2-way messaging)
- Twilio / MSG91 shape for SMS
- SMTP / Resend for email

### Deployment (for demo)
- Vercel for Next.js frontend
- Fly.io / Railway for FastAPI backend
- Neon / Supabase for Postgres
- Upstash for Redis

### Observability
- Structured logs (JSON) with case_id trace.
- Simple metrics dashboard: cases/min, LLM latency, bandit convergence, network alerts fired.

---

## 13. Build Phases

Compressed hackathon timeline. Adjust to your actual days.

### Phase 0 — Foundations (Day 1)
- Repo setup, Next.js + FastAPI scaffolding.
- Postgres schema + migrations (including ML tables).
- Basic auth (single-merchant login is fine for demo).

### Phase 1 — Event ingestion & simulator (Day 2)
- Webhook receiver endpoint.
- Event simulator (all four event types, with ground-truth counterfactual generation for uplift validation).
- Reply generator (Hinglish/multilingual with known intent labels).
- Case creation from events.

### Phase 2 — Agent core loop (Days 3-4)
- Detect → route to playbook.
- Deterministic guardrail layer.
- Execution adapters (all simulated but API-shaped).
- Audit logging with structured decision records.

### Phase 3 — LLM integration (Day 5)
- Diagnosis evidence extraction (with structured JSON output).
- Message generation (Hinglish, tone-adaptive).
- Reply classification (Hinglish/multilingual).
- Edge-case decision override.

### Phase 4 — Contextual bandit (Day 6)
- Bandit implementation (Thompson sampling per playbook).
- Context feature extraction.
- Reward wiring from outcomes.
- Bandit-decision path in the agent core.
- Bandit convergence visualization for dashboard.

### Phase 5 — Uplift modeling + Causal DAG (Day 7)
- Uplift holdout assignment (~5% of eligible cases).
- Simple T-learner uplift model + CATE estimation per context bucket.
- Uplift check gate in the agent core.
- Causal DAG hand-encoded per playbook.
- Bayesian updater + causal path traversal.
- Causal DAG visualization in the dashboard.

### Phase 6 — Federated intelligence layer (Day 8)
- Network stats aggregation.
- Time-series anomaly detector for downtime detection.
- Network alert broadcasting (via Redis pub/sub).
- Population priors for bandit warm-start.
- Network Intelligence dashboard panel.

### Phase 7 — Playbooks + scenarios (Day 9)
- All four playbooks fully configured.
- Six persona scenarios seeded and playable end-to-end.
- Three system-level demo beats (bandit curve, uplift panel, federated downtime).

### Phase 8 — Merchant dashboard polish (Days 10-11)
- Home / live ticker.
- Playbook config screens.
- Case detail with causal DAG + bandit alternatives + reply timeline.
- Network Intelligence panel.
- Uplift transparency page.
- Audit log viewer.
- Batch results screen.

### Phase 9 — Video & submission (Day 12)
- Rehearse all six persona scenarios + three system beats.
- Screen record with narration.
- Cut to 4-5 minutes.
- Write submission narrative.
- Deploy live demo.

**If time-tight:** the causal DAG is the first drop (fall back to LLM-only diagnosis, keep bandit + uplift + federated + reply intelligence). Every other component is essential to the differentiation story.

---

## 14. Video Plan (4-5 minutes)

### Structure

**[0:00 – 0:20] Hook — the problem**
- Fast montage: failed payment screen, abandoned cart, angry invoice email, cancelled subscription.
- VO: *"Every day, Indian merchants lose crores to revenue that just... slips away. Failed payments, dropped checkouts, broken mandates, unpaid invoices. What if Razorpay could close every leak — intelligently?"*

**[0:20 – 0:45] The pitch**
- Product name reveal: **Recover**.
- One sentence: *"An AI agent that lives on the Razorpay dashboard, learns from every case, respects when not to intervene, and gets smarter across Razorpay's entire network."*
- Quick visual of the architecture diagram, callouts on: bandit, causal DAG, uplift, federated intelligence.

**[0:45 – 2:30] The six persona scenarios**
- 15-18 seconds each.
- Split-screen where useful: customer's WhatsApp on one side, merchant dashboard on the other.
- Show the causal DAG lighting up. Show the bandit's arm choice with alternatives. Show the LLM's reply classification popping up.
- Vary the outcomes: some saves (Suresh, Priya, Aditya, Meera), one graceful human handoff (Vikram), one compliance stop (Sana).

**[2:30 – 3:00] System beat 1 — The bandit learning curve**
- Cut to the dashboard.
- Chart animates: LLM-only line flat at 22%, Recover line starts at 20%, crosses at ~200 cases, climbs to 38%.
- VO: *"The agent doesn't stay the same. Every case makes it sharper."*

**[3:00 – 3:30] System beat 2 — The uplift ROI panel**
- Two numbers on screen.
- VO: *"Everyone measures recovery. We measure recovery we actually caused. ₹9.2 lakhs incremental, not ₹14.8 lakhs gross. Honest ROI."*

**[3:30 – 4:00] System beat 3 — The federated downtime save**
- Live: SBI UPI degradation appears, network detects it, alert fires, retries pause across all merchants.
- VO: *"When SBI goes down at 3pm, our agent knows within 90 seconds — because we watch every Razorpay merchant, together. No merchant could see this alone. This is only possible on Razorpay."*

**[4:00 – 4:30] The trust story**
- Show the audit log with causal path.
- Show Sana's STOP being honored in seconds.
- Show Vikram's human handoff card.
- VO: *"Every decision is traceable. Every stop is honored. Every rupee moved has a reason."*

**[4:30 – 5:00] Close**
- Recap: 4 playbooks × contextual bandits × uplift-honest ROI × federated network intelligence × Hinglish reply understanding × compliance built in.
- Call to action: *"Recover — for every merchant, on every rail, for every rupee. And smarter every day."*

### Video production tips
- Use a real browser, real dashboard, real terminal — not mockups.
- Record at 1440p or higher, deliver at 1080p.
- Use consistent color coding: green = recovered, amber = in flight, red = at risk, gray = stopped, blue = holdout.
- When showing the causal DAG lighting up or bandit alternatives fanning out, slow down slightly — these are the "AI is real" moments.
- Music: subtle, not overpowering. Silence briefly for the compliance moments (Sana STOP, Vikram handoff) to give them weight.

---

## 15. Submission Deliverables

For the Razorpay form, prepare:

1. **Demo video** (4-5 min, MP4, uploaded to YouTube unlisted).
2. **Live demo URL** (dashboard deployed on Vercel + backend on Fly/Railway).
3. **GitHub repo** (public or shared with judges) with:
   - README with setup instructions
   - Architecture diagram
   - This plan.md
   - Working code
   - Simulator seed data
   - Bandit / uplift / federated methodology notes
4. **One-pager PDF** covering: problem, solution, why-Razorpay-specifically, results (₹ recovered, incremental recovery, compliance), architecture snapshot, ML methodology, next steps.
5. **Submission narrative** (whatever the form asks): 200-400 words covering the vision, the technical bar cleared (batch results, compliance, audit trail, bandit learning, uplift honesty, federated intelligence), and what would ship in production vs. what's simulated.

---

## 16. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Building four playbooks + real ML is too ambitious | Shared agent core makes playbooks tractable; ML libraries (causalml/vowpalwabbit) reduce implementation cost. Causal DAG is the first drop. |
| LLM outputs unreliable JSON | Structured output mode + JSON schema + rules fallback + log failures. |
| Bandit cold-start ruins early demo cases | Federated network priors warm-start the bandit — day-one intelligence is a feature, not a workaround. |
| Uplift measurement noisy in small samples | Report incremental recovery with confidence intervals; use context buckets not per-case estimates. |
| Simulator feels fake | Ground every number in a public Razorpay stat or industry benchmark; cite in the video and README; show the "true willingness to pay" ground-truth mechanism transparently. |
| Judges don't grasp the ML depth in a 5-min video | Include the "what makes us different" comparison table in the one-pager and README; the three system-level demo beats (bandit curve, uplift panel, federated downtime) are the ML story landing pads. |
| Demo LLM latency ruins pacing | Pre-compute demo cases and cache; live-run only 1-2 for the video. |
| Time overrun on dashboard polish | Use shadcn/ui components; don't over-design; the *intelligence* is the differentiator, not custom UI. |

---

## 17. What "done" looks like

- ✅ Four playbooks, one shared agent core, all working end-to-end.
- ✅ Six persona scenarios play back cleanly for the video.
- ✅ Three system-level demo beats (bandit curve, uplift panel, federated downtime) all functional.
- ✅ Batch of 1,000 simulated cases produces a real recovery rate ≥ 30% with incremental (uplift-adjusted) recovery ≥ 20%.
- ✅ Contextual bandit demonstrably outperforms LLM-only baseline over the batch.
- ✅ Uplift model reports honest incremental recovery, with holdout methodology transparent in the dashboard.
- ✅ Federated intelligence layer detects a simulated bank downtime and pauses retries platform-wide.
- ✅ Every decision has causal path + bandit alternatives + LLM reasoning visible in the audit trail.
- ✅ Compliance rules are enforced and demonstrated (STOP, RBI cap, TRAI hour, hardship handoff).
- ✅ Cross-merchant intelligence view shows Razorpay's unique moat.
- ✅ Dashboard is functional and screenshot-worthy.
- ✅ Video tells a clean story in under 5 minutes with the three ML system beats clearly landing.
- ✅ Repo is clean enough that a judge could clone and run it.

---

## Next steps

1. Sign off on this plan (or push back on anything).
2. Write `scenarios.md` — the fully scripted six persona scenarios + three system beats, with every LLM prompt/response, every bandit context vector, every WhatsApp message, every dashboard state — because that's what everything else has to match.
3. Decide on Thompson sampling vs. LinUCB for the bandit (Thompson is simpler and demos beautifully — bars showing arm posteriors visibly narrowing over time).
4. Kick off Phase 0 (repo scaffolding + Postgres schema including ML tables).
