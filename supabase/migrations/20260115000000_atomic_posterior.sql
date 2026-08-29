-- increment_bandit_posterior ---------------------------------------------------
-- Fold one observation into an arm's Beta posterior, atomically.
--
-- The Python this replaces was a read-modify-write: fetch alpha and beta, add
-- one to whichever the outcome favoured, write both back. Two cases closing in
-- the same instant both read the same alpha and both write the same alpha+1, so
-- one observation is lost. Nothing crashes and no error is logged — the bandit
-- simply learns more slowly than it should, in proportion to how busy the
-- merchant is, which is the hardest class of bug to notice.
--
-- Doing it as `alpha = alpha + p_alpha_inc` inside a single statement means
-- Postgres holds the row lock for the duration and the second writer reads the
-- first writer's value. The upsert and the increment become one round trip,
-- which is also one fewer network hop per closed case.
--
-- ON CONFLICT targets the table's own UNIQUE (merchant_id, playbook, arm_name,
-- context_bucket). An arm with no row yet is inserted at the flat Beta(1,1)
-- prior plus this observation, so a first success lands on Beta(2,1) rather than
-- on nothing — the same warm-start behaviour the Python had.
--
-- Idempotent by construction: CREATE OR REPLACE, so applying this migration
-- twice is a no-op rather than an error.
CREATE OR REPLACE FUNCTION public.increment_bandit_posterior(
  p_merchant_id    UUID,
  p_playbook       TEXT,
  p_arm_name       TEXT,
  p_context_bucket TEXT,
  p_alpha_inc      NUMERIC,
  p_beta_inc       NUMERIC
) RETURNS VOID AS $$
  INSERT INTO public.bandit_posteriors
    (merchant_id, playbook, arm_name, context_bucket,
     alpha, beta, n_pulls, last_updated_at, created_at, updated_at)
  VALUES
    (p_merchant_id, p_playbook, p_arm_name, p_context_bucket,
     1.0 + p_alpha_inc, 1.0 + p_beta_inc, 1, now(), now(), now())
  ON CONFLICT (merchant_id, playbook, arm_name, context_bucket)
  DO UPDATE SET
    alpha           = public.bandit_posteriors.alpha + p_alpha_inc,
    beta            = public.bandit_posteriors.beta  + p_beta_inc,
    n_pulls         = public.bandit_posteriors.n_pulls + 1,
    last_updated_at = now(),
    updated_at      = now();
$$ LANGUAGE SQL;

-- The service role runs the agent loop; `authenticated` is here so a merchant's
-- own session could post a reward if a future endpoint ever lets them.
GRANT EXECUTE ON FUNCTION public.increment_bandit_posterior(
  UUID, TEXT, TEXT, TEXT, NUMERIC, NUMERIC
) TO service_role, authenticated;
