-- ============================================================================
-- Recover — initial schema (FROZEN)
--
-- Every later phase is additive only: new migrations may ADD tables, columns,
-- indexes or policies, but must not rename or drop anything defined here.
--
-- Conventions used throughout:
--   * every table has id / created_at / updated_at and a set_updated_at trigger
--   * tenancy is a single UUID: merchants.id IS auth.users.id, so RLS is a
--     direct `merchant_id = auth.uid()` comparison with no join
--   * auth.uid() is wrapped in a scalar subquery so Postgres evaluates it once
--     per statement (initplan) instead of once per row
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ----------------------------------------------------------------------------
-- Shared trigger function
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TABLES
-- ============================================================================

-- merchants ------------------------------------------------------------------
-- id mirrors auth.users.id. Populated by the on_auth_user_created trigger.
CREATE TABLE public.merchants (
  id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  vertical        TEXT,          -- 'd2c_beauty' | 'edtech_subscription' | 'b2b_distribution' | 'other'
  onboarded       BOOLEAN NOT NULL DEFAULT false,
  playbook_config JSONB NOT NULL DEFAULT '{}'::jsonb,
  timezone        TEXT NOT NULL DEFAULT 'Asia/Kolkata',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- customers ------------------------------------------------------------------
CREATE TABLE public.customers (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id  UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  external_id  TEXT,            -- the merchant's own identifier for this customer
  name         TEXT,
  phone        TEXT,
  email        TEXT,
  ltv_cents    BIGINT NOT NULL DEFAULT 0,
  tenure_days  INT NOT NULL DEFAULT 0,
  consent      JSONB NOT NULL DEFAULT '{"whatsapp":true,"sms":true,"email":true,"marketing":false,"opted_out_at":null}'::jsonb,
  metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_customers_merchant_id ON public.customers (merchant_id);
CREATE INDEX idx_customers_merchant_external ON public.customers (merchant_id, external_id);

-- payment_methods ------------------------------------------------------------
CREATE TABLE public.payment_methods (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id      UUID NOT NULL REFERENCES public.customers(id) ON DELETE CASCADE,
  type             TEXT NOT NULL,   -- 'card' | 'upi' | 'netbanking' | 'wallet'
  bin              TEXT,
  bank             TEXT,
  last_used_at     TIMESTAMPTZ,
  success_rate_90d NUMERIC(4,3),
  metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_payment_methods_customer_id ON public.payment_methods (customer_id);

-- events ---------------------------------------------------------------------
CREATE TABLE public.events (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id  UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  customer_id  UUID REFERENCES public.customers(id) ON DELETE SET NULL,
  event_type   TEXT NOT NULL,   -- 'payment.failed' | 'checkout.abandoned' | 'subscription.charged.failed' | 'invoice.overdue' | 'customer.replied'
  payload      JSONB NOT NULL,
  received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_merchant_received ON public.events (merchant_id, received_at DESC);
CREATE INDEX idx_events_event_type ON public.events (event_type);
CREATE INDEX idx_events_customer_id ON public.events (customer_id);

-- recovery_cases -------------------------------------------------------------
CREATE TABLE public.recovery_cases (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id            UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  customer_id            UUID NOT NULL REFERENCES public.customers(id) ON DELETE CASCADE,
  playbook               TEXT NOT NULL,   -- 'failed_payment' | 'checkout_abandonment' | 'subscription_failure' | 'b2b_overdue'
  status                 TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'in_flight' | 'recovered' | 'stopped' | 'failed' | 'holdout'
  amount_at_risk_cents   BIGINT NOT NULL,
  amount_recovered_cents BIGINT NOT NULL DEFAULT 0,
  opened_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at              TIMESTAMPTZ,
  current_step           TEXT,
  diagnosis              JSONB,
  uplift_bucket          TEXT,   -- 'persuadable' | 'sure_thing' | 'lost_cause' | 'dnd' | 'unknown'
  is_holdout             BOOLEAN NOT NULL DEFAULT false,
  trigger_event_id       UUID REFERENCES public.events(id) ON DELETE SET NULL,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_recovery_cases_merchant_status ON public.recovery_cases (merchant_id, status);
CREATE INDEX idx_recovery_cases_merchant_opened ON public.recovery_cases (merchant_id, opened_at DESC);
CREATE INDEX idx_recovery_cases_customer_id ON public.recovery_cases (customer_id);
CREATE INDEX idx_recovery_cases_trigger_event_id ON public.recovery_cases (trigger_event_id);

-- agent_decisions ------------------------------------------------------------
-- One row per step of the agent loop. merchant_id is denormalised so RLS never
-- has to join back through recovery_cases.
CREATE TABLE public.agent_decisions (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id                UUID NOT NULL REFERENCES public.recovery_cases(id) ON DELETE CASCADE,
  merchant_id            UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  step_number            INT NOT NULL,
  step_name              TEXT NOT NULL,   -- 'detect' | 'diagnose' | 'uplift_check' | 'decide' | 'guardrail' | 'execute' | 'listen' | 'learn'
  decision_source        TEXT,            -- 'bandit' | 'llm' | 'rule' | 'human' | 'system'
  bandit_context_vector  JSONB,
  bandit_chosen_arm      TEXT,
  bandit_arm_confidence  NUMERIC(4,3),
  bandit_mode            TEXT,            -- 'exploit' | 'explore'
  bandit_alternatives    JSONB,
  llm_prompt_hash        TEXT,
  llm_response           JSONB,
  causal_path            JSONB,
  diagnosis_posteriors   JSONB,
  chosen_action          TEXT,
  action_params          JSONB,
  reasoning              TEXT,
  uplift_estimate        NUMERIC(4,3),
  guardrail_checks       JSONB,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_agent_decisions_case_step ON public.agent_decisions (case_id, step_number);
CREATE INDEX idx_agent_decisions_merchant_id ON public.agent_decisions (merchant_id);

-- execution_attempts ---------------------------------------------------------
CREATE TABLE public.execution_attempts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id          UUID NOT NULL REFERENCES public.recovery_cases(id) ON DELETE CASCADE,
  merchant_id      UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  decision_id      UUID REFERENCES public.agent_decisions(id) ON DELETE SET NULL,
  action_type      TEXT NOT NULL,   -- 'retry_charge' | 'send_payment_link' | 'send_whatsapp' | 'send_sms' | 'send_email' | 'mandate_reregister' | 'human_handoff' | 'no_op'
  adapter          TEXT NOT NULL,   -- 'razorpay_pg' | 'razorpay_subscriptions' | 'razorpay_payment_links' | 'whatsapp_business' | 'twilio_sms' | 'smtp'
  request_payload  JSONB,
  response_payload JSONB,
  status           TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'success' | 'failure' | 'cancelled'
  idempotency_key  TEXT UNIQUE,
  attempted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at     TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_execution_attempts_case_id ON public.execution_attempts (case_id);
CREATE INDEX idx_execution_attempts_merchant_id ON public.execution_attempts (merchant_id);
CREATE INDEX idx_execution_attempts_decision_id ON public.execution_attempts (decision_id);

-- customer_replies -----------------------------------------------------------
CREATE TABLE public.customer_replies (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id              UUID NOT NULL REFERENCES public.recovery_cases(id) ON DELETE CASCADE,
  merchant_id          UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  customer_id          UUID REFERENCES public.customers(id) ON DELETE SET NULL,
  channel              TEXT NOT NULL,   -- 'whatsapp' | 'sms' | 'email' | 'voice'
  raw_text             TEXT NOT NULL,
  llm_classification   JSONB,
  applied_state_update TEXT,
  received_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_customer_replies_case_id ON public.customer_replies (case_id);
CREATE INDEX idx_customer_replies_merchant_id ON public.customer_replies (merchant_id);
CREATE INDEX idx_customer_replies_customer_id ON public.customer_replies (customer_id);

-- audit_events ---------------------------------------------------------------
CREATE TABLE public.audit_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id     UUID REFERENCES public.recovery_cases(id) ON DELETE CASCADE,
  merchant_id UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  actor       TEXT NOT NULL,   -- 'agent' | 'human' | 'system' | 'customer'
  event       TEXT NOT NULL,
  details     JSONB,
  trace_id    TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_events_case_id ON public.audit_events (case_id);
CREATE INDEX idx_audit_events_merchant_created ON public.audit_events (merchant_id, created_at DESC);
CREATE INDEX idx_audit_events_trace_id ON public.audit_events (trace_id);

-- bandit_arms ----------------------------------------------------------------
-- Global reference data: the action catalogue every merchant's bandit draws from.
CREATE TABLE public.bandit_arms (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  playbook               TEXT NOT NULL,
  arm_name               TEXT NOT NULL,
  action_type            TEXT NOT NULL,
  action_params_template JSONB,
  active                 BOOLEAN NOT NULL DEFAULT true,
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (playbook, arm_name)
);

-- bandit_rewards -------------------------------------------------------------
CREATE TABLE public.bandit_rewards (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id    UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  case_id        UUID NOT NULL REFERENCES public.recovery_cases(id) ON DELETE CASCADE,
  decision_id    UUID REFERENCES public.agent_decisions(id) ON DELETE SET NULL,
  arm_name       TEXT NOT NULL,
  context_vector JSONB NOT NULL,
  context_bucket TEXT NOT NULL,   -- hashed bucket used to group similar contexts
  reward_value   NUMERIC NOT NULL,
  reward_type    TEXT NOT NULL DEFAULT 'binary',  -- 'binary' | 'amount_normalized'
  observed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_bandit_rewards_merchant_arm_bucket ON public.bandit_rewards (merchant_id, arm_name, context_bucket);
CREATE INDEX idx_bandit_rewards_case_id ON public.bandit_rewards (case_id);
CREATE INDEX idx_bandit_rewards_decision_id ON public.bandit_rewards (decision_id);

-- bandit_posteriors ----------------------------------------------------------
-- Beta(alpha, beta) per (merchant, playbook, arm, context bucket).
CREATE TABLE public.bandit_posteriors (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id     UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  playbook        TEXT NOT NULL,
  arm_name        TEXT NOT NULL,
  context_bucket  TEXT NOT NULL,
  alpha           NUMERIC NOT NULL DEFAULT 1.0,
  beta            NUMERIC NOT NULL DEFAULT 1.0,
  n_pulls         INT NOT NULL DEFAULT 0,
  last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (merchant_id, playbook, arm_name, context_bucket)
);
CREATE INDEX idx_bandit_posteriors_merchant_playbook ON public.bandit_posteriors (merchant_id, playbook);

-- uplift_holdouts ------------------------------------------------------------
CREATE TABLE public.uplift_holdouts (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id              UUID NOT NULL UNIQUE REFERENCES public.recovery_cases(id) ON DELETE CASCADE,
  merchant_id          UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  assigned_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  holdout_reason       TEXT,
  outcome              TEXT,   -- 'recovered' | 'not_recovered' | 'unknown'
  outcome_amount_cents BIGINT,
  context_features     JSONB,
  used_in_training     BOOLEAN NOT NULL DEFAULT false,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_uplift_holdouts_merchant_id ON public.uplift_holdouts (merchant_id);

-- uplift_model_snapshots -----------------------------------------------------
CREATE TABLE public.uplift_model_snapshots (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id          UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  playbook             TEXT NOT NULL,
  trained_at           TIMESTAMPTZ NOT NULL,
  model_type           TEXT NOT NULL,   -- 't_learner' | 'x_learner' | 'causal_tree'
  feature_importances  JSONB,
  bucket_uplifts       JSONB,
  training_sample_size INT NOT NULL,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_uplift_snapshots_merchant_playbook_trained ON public.uplift_model_snapshots (merchant_id, playbook, trained_at DESC);

-- causal_dag -----------------------------------------------------------------
-- Global reference data: the diagnosis graph, one row per node per playbook.
CREATE TABLE public.causal_dag (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  playbook          TEXT NOT NULL,
  node_id           TEXT NOT NULL,
  node_type         TEXT NOT NULL,   -- 'root_cause' | 'observable' | 'intervention' | 'outcome'
  parents           JSONB NOT NULL DEFAULT '[]'::jsonb,  -- array of node_id strings
  prior_probability NUMERIC(4,3),
  metadata          JSONB,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (playbook, node_id)
);

-- causal_edge_updates --------------------------------------------------------
-- Per-merchant learned edge weights layered on top of the global DAG priors.
CREATE TABLE public.causal_edge_updates (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id           UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  playbook              TEXT NOT NULL,
  from_node             TEXT NOT NULL,
  to_node               TEXT NOT NULL,
  observed_transitions  INT NOT NULL DEFAULT 0,
  total_observations    INT NOT NULL DEFAULT 0,
  last_updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (merchant_id, playbook, from_node, to_node)
);
CREATE INDEX idx_causal_edge_updates_merchant_id ON public.causal_edge_updates (merchant_id);

-- network_stats --------------------------------------------------------------
-- Cross-merchant aggregate. Readable by all, written by service role only.
CREATE TABLE public.network_stats (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bank               TEXT NOT NULL,
  method             TEXT NOT NULL,
  hour_of_day        INT NOT NULL CHECK (hour_of_day BETWEEN 0 AND 23),
  day_of_week        INT NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),  -- Monday = 0
  merchant_size_class TEXT,   -- 'small' | 'medium' | 'large'
  success_rate       NUMERIC(4,3) NOT NULL,
  sample_size        INT NOT NULL,
  window_start       TIMESTAMPTZ NOT NULL,
  window_end         TIMESTAMPTZ NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_network_stats_bank_method_hour ON public.network_stats (bank, method, hour_of_day);
CREATE INDEX idx_network_stats_window_end ON public.network_stats (window_end DESC);

-- network_alerts -------------------------------------------------------------
CREATE TABLE public.network_alerts (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alert_type                TEXT NOT NULL,   -- 'downtime' | 'degradation' | 'anomaly' | 'recovery'
  affected_bank             TEXT,
  affected_method           TEXT,
  severity                  TEXT NOT NULL,   -- 'low' | 'medium' | 'high' | 'critical'
  z_score                   NUMERIC,
  sample_size               INT,
  affected_merchants_count  INT,
  network_wide_success_rate NUMERIC(4,3),
  baseline_rate             NUMERIC(4,3),
  detected_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  resolved_at               TIMESTAMPTZ,
  metadata                  JSONB,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_network_alerts_detected_at ON public.network_alerts (detected_at DESC);
CREATE INDEX idx_network_alerts_open ON public.network_alerts (affected_bank, affected_method) WHERE resolved_at IS NULL;

-- llm_cache ------------------------------------------------------------------
CREATE TABLE public.llm_cache (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt_hash    TEXT NOT NULL UNIQUE,
  prompt_preview TEXT NOT NULL,   -- first 200 chars, for debugging only
  model          TEXT NOT NULL,
  response       JSONB NOT NULL,
  input_tokens   INT,
  output_tokens  INT,
  latency_ms     INT,
  hit_count      INT NOT NULL DEFAULT 0,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- The UNIQUE constraint above already provides the prompt_hash lookup index.

-- ============================================================================
-- updated_at TRIGGERS
-- ============================================================================

CREATE TRIGGER set_updated_at_merchants              BEFORE UPDATE ON public.merchants              FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_customers              BEFORE UPDATE ON public.customers              FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_payment_methods        BEFORE UPDATE ON public.payment_methods        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_events                 BEFORE UPDATE ON public.events                 FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_recovery_cases         BEFORE UPDATE ON public.recovery_cases         FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_agent_decisions        BEFORE UPDATE ON public.agent_decisions        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_execution_attempts     BEFORE UPDATE ON public.execution_attempts     FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_customer_replies       BEFORE UPDATE ON public.customer_replies       FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_audit_events           BEFORE UPDATE ON public.audit_events           FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_bandit_arms            BEFORE UPDATE ON public.bandit_arms            FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_bandit_rewards         BEFORE UPDATE ON public.bandit_rewards         FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_bandit_posteriors      BEFORE UPDATE ON public.bandit_posteriors      FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_uplift_holdouts        BEFORE UPDATE ON public.uplift_holdouts        FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_uplift_model_snapshots BEFORE UPDATE ON public.uplift_model_snapshots FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_causal_dag             BEFORE UPDATE ON public.causal_dag             FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_causal_edge_updates    BEFORE UPDATE ON public.causal_edge_updates    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_network_stats          BEFORE UPDATE ON public.network_stats          FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_network_alerts         BEFORE UPDATE ON public.network_alerts         FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER set_updated_at_llm_cache              BEFORE UPDATE ON public.llm_cache              FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================

ALTER TABLE public.merchants              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customers              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payment_methods        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.events                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.recovery_cases         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_decisions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.execution_attempts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_replies       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_events           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bandit_arms            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bandit_rewards         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bandit_posteriors      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.uplift_holdouts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.uplift_model_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.causal_dag             ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.causal_edge_updates    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.network_stats          ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.network_alerts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.llm_cache              ENABLE ROW LEVEL SECURITY;

-- merchants: a user sees exactly their own row -------------------------------
CREATE POLICY "own_merchant_row" ON public.merchants
  FOR ALL USING (id = (SELECT auth.uid())) WITH CHECK (id = (SELECT auth.uid()));

-- merchant-scoped tables -----------------------------------------------------
CREATE POLICY "merchant_isolation" ON public.customers
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.events
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.recovery_cases
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.agent_decisions
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.execution_attempts
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.customer_replies
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.audit_events
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.bandit_rewards
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.bandit_posteriors
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.uplift_holdouts
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.uplift_model_snapshots
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));
CREATE POLICY "merchant_isolation" ON public.causal_edge_updates
  FOR ALL USING (merchant_id = (SELECT auth.uid())) WITH CHECK (merchant_id = (SELECT auth.uid()));

-- payment_methods has no merchant_id — isolate through its customer ----------
CREATE POLICY "merchant_isolation_via_customer" ON public.payment_methods
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM public.customers c
      WHERE c.id = payment_methods.customer_id
        AND c.merchant_id = (SELECT auth.uid())
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.customers c
      WHERE c.id = payment_methods.customer_id
        AND c.merchant_id = (SELECT auth.uid())
    )
  );

-- Global reference tables: readable by any signed-in user, written by the
-- service role only (which bypasses RLS entirely, so no write policy exists).
CREATE POLICY "authenticated_read" ON public.bandit_arms
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read" ON public.causal_dag
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read" ON public.network_stats
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read" ON public.network_alerts
  FOR SELECT USING (auth.role() = 'authenticated');
CREATE POLICY "authenticated_read" ON public.llm_cache
  FOR SELECT USING (auth.role() = 'authenticated');

-- ============================================================================
-- AUTH HOOK — create the merchant row on signup
-- ============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.merchants (id, name, vertical, onboarded)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'name', 'My Business'), NULL, false);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
