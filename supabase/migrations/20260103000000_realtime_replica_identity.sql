-- ============================================================================
-- Realtime: replica identity and publication membership
-- ============================================================================
--
-- Supabase Realtime reads the Postgres logical replication stream. Two things
-- have to be true for a table to appear in it:
--
--   1. The table is a member of the `supabase_realtime` publication.
--   2. Its REPLICA IDENTITY is FULL.
--
-- The second is the part that is easy to get wrong. The default identity is
-- `DEFAULT`, which puts only the primary key in the WAL record for an UPDATE.
-- A subscriber then learns that a row changed but not what it changed *from* —
-- and every one of these three tables is watched precisely for its transitions:
-- a case going open -> in_flight, an audit row landing, an event being marked
-- processed. FULL logs the whole old row, which is what makes `old_record`
-- populated on the client.
--
-- FULL is not free: it widens every UPDATE's WAL record. That is the right
-- trade here because these tables are low-volume by construction — one row per
-- recovery, one per agent step — and the alternative is a live view that cannot
-- tell an insert from an update.
--
-- Applying this migration is enough; no dashboard toggling is required. It is
-- written to be idempotent so a re-run against a project that was configured by
-- hand does not fail.
--
-- The subscription code itself ships in Phase 8. Until then the pages fetch on
-- the server, which is correct for Phase 4 — this migration only makes sure the
-- database is ready when that lands.
-- ============================================================================

ALTER TABLE public.recovery_cases REPLICA IDENTITY FULL;
ALTER TABLE public.audit_events   REPLICA IDENTITY FULL;
ALTER TABLE public.events         REPLICA IDENTITY FULL;

-- `ALTER PUBLICATION ... ADD TABLE` errors if the table is already a member, and
-- there is no IF NOT EXISTS for it, so membership is checked first.
DO $$
DECLARE
  target_table text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    -- A local `supabase start` creates this publication; a bare Postgres does
    -- not. Creating it empty keeps the migration runnable against both.
    CREATE PUBLICATION supabase_realtime;
  END IF;

  FOREACH target_table IN ARRAY ARRAY['recovery_cases', 'audit_events', 'events'] LOOP
    IF NOT EXISTS (
      SELECT 1 FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime'
        AND schemaname = 'public'
        AND tablename = target_table
    ) THEN
      EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE public.%I', target_table);
    END IF;
  END LOOP;
END $$;
