"use client";

import { useCallback, useEffect, useState } from "react";

import type { BatchRun } from "@/lib/api/batch";
import { fetchBatch } from "@/lib/api/batch";
import { createClient } from "@/lib/supabase/client";

/**
 * Follow one batch run to completion.
 *
 * **The row is subscribed to, and the payload is used.** This is the one place
 * in the app where a Realtime payload is read directly rather than triggering a
 * re-read — `useRealtimeCases` deliberately does the opposite, because a case
 * row arrives without the customer join every screen renders. A `batch_runs`
 * row has no joins: `result` is the whole thing the page draws. Re-reading on
 * every tick would mean an HTTP round trip per hundred cases to fetch a row the
 * database just handed over.
 *
 * That only works because the migration sets `REPLICA IDENTITY FULL`. Without
 * it Postgres replicates the primary key alone on an update, `result` arrives
 * undefined, and the progress bar sits at zero while the run completes behind
 * it — a failure with no error anywhere.
 *
 * A poll runs alongside at a slow interval. Realtime is the fast path, not a
 * guarantee: a dropped connection during a ninety-second run would otherwise
 * leave the page on a progress bar forever, and the fallback turns that into a
 * few seconds of staleness instead.
 */
const POLL_MS = 5000;

export function useBatchRun(initial: BatchRun | null) {
  const [run, setRun] = useState<BatchRun | null>(initial);

  const follow = useCallback((next: BatchRun) => setRun(next), []);

  useEffect(() => {
    const batchId = run?.batchId;
    if (!batchId || run?.status !== "running") return;

    const supabase = createClient();
    const channel = supabase
      .channel(`batch-run-${batchId}`)
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "batch_runs",
          filter: `id=eq.${batchId}`,
        },
        (payload) => {
          const row = payload.new as Record<string, unknown>;
          setRun((current) =>
            current && current.batchId === batchId
              ? {
                  ...current,
                  status: (row.status as BatchRun["status"]) ?? current.status,
                  result: (row.result as BatchRun["result"]) ?? current.result,
                  completedAt: (row.completed_at as string | null) ?? current.completedAt,
                  error: (row.error as string | null) ?? current.error,
                }
              : current,
          );
        },
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [run?.batchId, run?.status]);

  // Both effects key on the run's id *and* its status, so completing tears the
  // channel and the interval down without either needing to check for itself.
  useEffect(() => {
    const batchId = run?.batchId;
    if (!batchId || run?.status !== "running") return;

    const timer = setInterval(() => {
      void fetchBatch(batchId)
        .then((next) => setRun((current) => (current?.batchId === batchId ? next : current)))
        .catch(() => {
          // A failed poll is not a failed run. Realtime is still connected and
          // the next tick will try again.
        });
    }, POLL_MS);

    return () => clearInterval(timer);
  }, [run?.batchId, run?.status]);

  return { run, follow };
}
