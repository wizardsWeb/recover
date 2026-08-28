-- Per-case working state the agent accumulates between passes.
--
-- Phase 7 needs somewhere to record a promise to pay: a customer who answers
-- "50% abhi kar deti hoon, baaki 25 tak" has not paid and has not refused, and
-- the case must stay open, remember the terms, and stop pressing until the
-- promised date. None of the existing columns can hold that — `diagnosis` is
-- the agent's reading of the cause, and `current_step` is a single string.
--
-- JSONB rather than typed columns because this is genuinely open-ended state
-- that later phases will add to (promise tracking now, holdout assignment and
-- uplift scoring later), and a migration per field would be churn for data no
-- query filters on. Anything that needs an index gets promoted to a real column
-- when that need appears.
--
-- NOTE on a name collision worth knowing about: the agent loop's in-memory case
-- dict also carries a `metadata` key, built by `core._enrich_case`, and that one
-- holds the *trigger event's payload*. They are different things. The column is
-- read from the row; the dict key is read inside a pass. See `_enrich_case`.
ALTER TABLE public.recovery_cases
  ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
