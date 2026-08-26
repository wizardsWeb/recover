-- A minimal stand-in for the parts of Supabase that the migration depends on,
-- so the schema can be applied to a plain Postgres container and checked.
-- Never run this against a real Supabase project — it already has the real ones.

CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT,
  raw_user_meta_data JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Supabase derives these from the request's JWT. Here they read the same
-- session settings PostgREST would set, so policies behave identically.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS UUID AS $$
  SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$ LANGUAGE sql STABLE;

CREATE OR REPLACE FUNCTION auth.role() RETURNS TEXT AS $$
  SELECT COALESCE(NULLIF(current_setting('request.jwt.claim.role', true), ''), 'anon');
$$ LANGUAGE sql STABLE;

-- Supabase's request role. Table grants cannot happen here — this file runs
-- before the migration, so there is nothing yet to grant on. rls_isolation.sql
-- does it once the tables exist.
CREATE ROLE authenticated NOLOGIN;
GRANT USAGE ON SCHEMA public, auth TO authenticated;
