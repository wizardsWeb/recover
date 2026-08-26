-- ============================================================================
-- Recover — bandit arm catalogue (reference data)
--
-- `bandit_arms` is the action space: for each playbook, every move the
-- contextual bandit is allowed to consider. It is global reference data, not
-- merchant data — every merchant's posteriors are keyed against these same arm
-- names, which is what makes cross-merchant comparison meaningful later.
--
-- Seeded once here. Later phases may ADD arms in their own migration; nothing
-- in this file may be renamed or dropped, because `bandit_posteriors.arm_name`
-- and `bandit_rewards.arm_name` reference these strings by value.
--
-- ON CONFLICT DO NOTHING against the UNIQUE (playbook, arm_name) constraint
-- keeps a re-run idempotent, so `supabase db reset` and a forward-only migrate
-- both land in the same state.
--
-- `action_params_template` is the default parameter set the executor fills in
-- at dispatch time. It is a template, not the final payload: the agent overlays
-- case-specific values (payment link URL, inferred retry timestamp, message
-- body) on top of it.
-- ============================================================================

INSERT INTO public.bandit_arms (playbook, arm_name, action_type, action_params_template) VALUES

-- failed_payment -------------------------------------------------------------
-- A one-time payment failed. The lever is *when* and *how hard* to re-ask.
  ('failed_payment', 'retry_now',                     'retry_charge',      '{"delay_minutes": 0}'::jsonb),
  ('failed_payment', 'retry_at_optimal_hour',         'retry_charge',      '{"schedule": "network_optimal_hour", "max_wait_hours": 48}'::jsonb),
  ('failed_payment', 'silent_retry_next_morning',     'retry_charge',      '{"schedule": "next_business_morning", "local_hour": 9, "notify": false}'::jsonb),
  ('failed_payment', 'whatsapp_payment_link',         'send_payment_link', '{"channel": "whatsapp", "link_expiry_hours": 48}'::jsonb),
  ('failed_payment', 'sms_payment_link',              'send_payment_link', '{"channel": "sms", "link_expiry_hours": 48}'::jsonb),
  ('failed_payment', 'email_payment_link',            'send_payment_link', '{"channel": "email", "link_expiry_hours": 72}'::jsonb),
  ('failed_payment', 'switch_method_upi',             'send_payment_link', '{"channel": "whatsapp", "suggested_method": "upi", "link_expiry_hours": 48}'::jsonb),
  ('failed_payment', 'no_op',                         'no_op',             '{}'::jsonb),

-- checkout_abandonment -------------------------------------------------------
-- The cart is still warm. The lever is discount magnitude vs. margin.
  ('checkout_abandonment', 'whatsapp_saved_cart_no_discount', 'send_whatsapp',  '{"channel": "whatsapp", "discount_pct": 0}'::jsonb),
  ('checkout_abandonment', 'whatsapp_saved_cart_5pct',        'send_whatsapp',  '{"channel": "whatsapp", "discount_pct": 5}'::jsonb),
  ('checkout_abandonment', 'whatsapp_saved_cart_8pct',        'send_whatsapp',  '{"channel": "whatsapp", "discount_pct": 8}'::jsonb),
  ('checkout_abandonment', 'whatsapp_saved_cart_12pct',       'send_whatsapp',  '{"channel": "whatsapp", "discount_pct": 12}'::jsonb),
  ('checkout_abandonment', 'email_saved_cart',                'send_email',     '{"channel": "email", "discount_pct": 0}'::jsonb),
  ('checkout_abandonment', 'sms_saved_cart',                  'send_sms',       '{"channel": "sms", "discount_pct": 0}'::jsonb),
  ('checkout_abandonment', 'suggest_alternate_method',        'send_whatsapp',  '{"channel": "whatsapp", "discount_pct": 0, "suggest_methods": ["upi", "netbanking"]}'::jsonb),
  ('checkout_abandonment', 'no_op',                           'no_op',          '{}'::jsonb),

-- subscription_failure -------------------------------------------------------
-- A mandate broke. The lever is timing against the payer's cash cycle, and
-- knowing when to stop and involve a human.
  ('subscription_failure', 'immediate_retry',                                'retry_charge',       '{"delay_minutes": 0}'::jsonb),
  ('subscription_failure', 'retry_at_inferred_date',                         'retry_charge',       '{"schedule": "inferred_salary_date", "local_hour": 9}'::jsonb),
  ('subscription_failure', 'retry_at_inferred_date_plus_whatsapp_fallback',  'retry_charge',       '{"schedule": "inferred_salary_date", "local_hour": 9, "fallback": {"channel": "whatsapp", "after_hours": 24}}'::jsonb),
  ('subscription_failure', 'whatsapp_payment_link_now',                      'send_payment_link',  '{"channel": "whatsapp", "link_expiry_hours": 48}'::jsonb),
  ('subscription_failure', 'dunning_email_sequence',                         'send_email',         '{"channel": "email", "steps": 3, "gap_days": 3}'::jsonb),
  ('subscription_failure', 'mandate_reregistration',                         'mandate_reregister', '{"channel": "whatsapp", "link_expiry_hours": 72}'::jsonb),
  ('subscription_failure', 'pause_with_winback',                             'no_op',              '{"pause_months": 3, "winback_after_days": 90}'::jsonb),
  ('subscription_failure', 'human_handoff',                                  'human_handoff',      '{"queue": "retention", "sla_hours": 48}'::jsonb),

-- b2b_overdue ----------------------------------------------------------------
-- An invoice is late. The lever is tone escalation and payment flexibility,
-- across a relationship worth more than any single invoice.
  ('b2b_overdue', 'polite_reminder_whatsapp',          'send_whatsapp',     '{"channel": "whatsapp", "tone": "polite", "business_hours_only": true}'::jsonb),
  ('b2b_overdue', 'polite_reminder_email',             'send_email',        '{"channel": "email", "tone": "polite"}'::jsonb),
  ('b2b_overdue', 'firm_reminder_whatsapp',            'send_whatsapp',     '{"channel": "whatsapp", "tone": "firm", "business_hours_only": true}'::jsonb),
  ('b2b_overdue', 'firm_reminder_whatsapp_plus_email', 'send_whatsapp',     '{"channel": "whatsapp", "tone": "firm", "also_email": true, "business_hours_only": true}'::jsonb),
  ('b2b_overdue', 'partial_payment_offer',             'send_payment_link', '{"channel": "whatsapp", "min_partial_pct": 50, "link_expiry_hours": 168}'::jsonb),
  ('b2b_overdue', 'payment_plan_offer',                'send_payment_link', '{"channel": "whatsapp", "instalments": 3, "gap_days": 15}'::jsonb),
  ('b2b_overdue', 'accept_promise_to_pay',             'no_op',             '{"followup_after_days": 7}'::jsonb),
  ('b2b_overdue', 'escalate_to_human_ar',              'human_handoff',     '{"queue": "accounts_receivable", "sla_hours": 24}'::jsonb),
  ('b2b_overdue', 'graduated_b2b_sequence',            'send_whatsapp',     '{"channel": "whatsapp", "sequence": [{"day": 0, "tone": "polite"}, {"day": 5, "tone": "firm"}, {"day": 10, "offer": "partial_payment"}], "business_hours_only": true}'::jsonb)

ON CONFLICT (playbook, arm_name) DO NOTHING;
