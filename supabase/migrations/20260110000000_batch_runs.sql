-- batch_runs -----------------------------------------------------------------
-- One row per batch simulation. The row is both the progress channel and the
-- result store: `result` holds a partial `{progress: ...}` object while the run
-- is in flight and is replaced wholesale by the finished `BatchResult`. One
-- record means the frontend subscribes once and reads both from the same place,
-- rather than polling a status endpoint and a result endpoint that can disagree.
CREATE TABLE public.batch_runs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id  UUID NOT NULL REFERENCES public.merchants(id) ON DELETE CASCADE,
  status       TEXT NOT NULL DEFAULT 'running',  -- 'running' | 'completed' | 'failed'
  n_cases      INT NOT NULL,
  result       JSONB,
  error        TEXT,
  started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The frontend's only query is "my most recent run", newest first.
CREATE INDEX idx_batch_runs_merchant_started ON public.batch_runs (merchant_id, started_at DESC);

ALTER TABLE public.batch_runs ENABLE ROW LEVEL SECURITY;

-- Same shape as every other per-merchant table: the row is visible to the
-- merchant it belongs to and to nobody else. The service role bypasses this,
-- which is what lets the background runner write progress without a session.
CREATE POLICY "merchant_isolation" ON public.batch_runs
  FOR ALL USING (merchant_id = auth.uid());

-- Realtime sends only the primary key on an UPDATE unless the whole row is
-- replicated. The frontend reads `result` off the change payload to move the
-- progress bar, so without this it would receive an id and have to fetch the
-- row it was just told about — one round trip per progress tick, which is the
-- polling this table exists to avoid.
ALTER TABLE public.batch_runs REPLICA IDENTITY FULL;

-- Synthetic cases written by a batch run are flagged in `recovery_cases`
-- metadata. Every read that reports money filters them out; this index is what
-- keeps that filter from turning into a sequential scan once a few batch runs
-- have happened.
CREATE INDEX idx_recovery_cases_batch_synthetic
  ON public.recovery_cases ((metadata ->> 'is_batch_synthetic'));
