-- Proves that tenant isolation is enforced by the database, not by application
-- code. Every assertion below fails loudly if a policy regresses.
--
-- Run against a throwaway Postgres that already has auth_stub.sql and the
-- migration applied — see supabase/tests/README.md.

\set ON_ERROR_STOP on

\echo '--- setup ---'

-- Table-level grants are what RLS filters *within*; without them the role is
-- refused outright and the policies never get a say.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;

INSERT INTO auth.users (id, email, raw_user_meta_data) VALUES
  ('11111111-1111-1111-1111-111111111111', 'alpha@example.com', '{"name":"Alpha Cosmetics"}'),
  ('22222222-2222-2222-2222-222222222222', 'beta@example.com',  '{}');

-- The signup trigger should have created a merchant row for each, naming it
-- from the metadata when present and falling back when not.
DO $$
DECLARE alpha_name TEXT; beta_name TEXT;
BEGIN
  SELECT name INTO alpha_name FROM public.merchants WHERE id = '11111111-1111-1111-1111-111111111111';
  SELECT name INTO beta_name  FROM public.merchants WHERE id = '22222222-2222-2222-2222-222222222222';
  ASSERT alpha_name = 'Alpha Cosmetics', format('expected metadata name, got %L', alpha_name);
  ASSERT beta_name  = 'My Business',     format('expected fallback name, got %L', beta_name);
END $$;

INSERT INTO public.customers (merchant_id, name) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Alpha customer'),
  ('22222222-2222-2222-2222-222222222222', 'Beta customer');

\echo '--- reads are scoped to the caller ---'

-- The table owner bypasses RLS, so every check below has to run as a role that
-- does not own the tables. This is the single most important line in the file.
SET ROLE authenticated;
SET request.jwt.claim.role = 'authenticated';
SET request.jwt.claim.sub  = '11111111-1111-1111-1111-111111111111';

DO $$
DECLARE merchants_seen INT; customers_seen INT; who TEXT;
BEGIN
  SELECT count(*) INTO merchants_seen FROM public.merchants;
  SELECT count(*), min(name) INTO customers_seen, who FROM public.customers;
  ASSERT merchants_seen = 1, format('alpha saw %s merchant rows, expected 1', merchants_seen);
  ASSERT customers_seen = 1, format('alpha saw %s customer rows, expected 1', customers_seen);
  ASSERT who = 'Alpha customer', format('alpha saw %L', who);
END $$;

SET request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';

DO $$
DECLARE who TEXT;
BEGIN
  SELECT min(name) INTO who FROM public.customers;
  ASSERT who = 'Beta customer', format('beta saw %L', who);
END $$;

\echo '--- writes cannot cross a tenant boundary ---'

SET request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';

DO $$
BEGIN
  INSERT INTO public.customers (merchant_id, name)
  VALUES ('22222222-2222-2222-2222-222222222222', 'smuggled');
  RAISE EXCEPTION 'alpha wrote a row into beta''s tenant — WITH CHECK is not doing its job';
EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'cross-tenant insert correctly rejected';
END $$;

\echo '--- shared reference tables are readable but not writable ---'

DO $$
BEGIN
  PERFORM count(*) FROM public.bandit_arms;  -- allowed
  INSERT INTO public.bandit_arms (playbook, arm_name, action_type)
  VALUES ('failed_payment', 'sneaky', 'no_op');
  RAISE EXCEPTION 'authenticated wrote to bandit_arms — it should be service-role only';
EXCEPTION WHEN insufficient_privilege THEN
  RAISE NOTICE 'shared-table write correctly rejected';
END $$;

RESET ROLE;

\echo '--- every public table has RLS on ---'

DO $$
DECLARE unprotected TEXT;
BEGIN
  SELECT string_agg(tablename, ', ') INTO unprotected
  FROM pg_tables WHERE schemaname = 'public' AND rowsecurity = false;
  ASSERT unprotected IS NULL, format('tables without RLS: %s', unprotected);
END $$;

\echo 'ALL RLS CHECKS PASSED'
