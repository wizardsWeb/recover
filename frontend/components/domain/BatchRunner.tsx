"use client";

/**
 * The batch page's three states, and the transitions between them.
 *
 * Empty, running, complete. They are branches on the *shape of the result*
 * rather than on a status string, because a Realtime update carries both and
 * they can arrive a moment apart — branching on status alone leaves a frame
 * where a finished result renders under a progress bar.
 *
 * A previous run's results stay on screen while a new one is in flight, dimmed
 * and labelled. The alternative is blanking the page for ninety seconds, which
 * throws away the thing the viewer was looking at in order to show them a
 * progress bar.
 */

import { useEffect, useState } from "react";
import { Play, PlayCircle, RotateCw, TriangleAlert } from "lucide-react";
import { toast } from "sonner";

import { BatchLearningCurve } from "@/components/domain/BatchLearningCurve";
import { BatchResultsSummary } from "@/components/domain/BatchResultsSummary";
import { EmptyState } from "@/components/empty-states/EmptyState";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { BatchRun } from "@/lib/api/batch";
import { fetchBatch, isComplete, isProgress, startBatch } from "@/lib/api/batch";
import { useBatchRun } from "@/lib/hooks/useBatchRun";
import { formatPercent } from "@/lib/utils/format";

const DEFAULT_CASES = 1000;

function ProgressPanel({ run }: { run: BatchRun }) {
  const progress = isProgress(run.result) ? run.result : null;
  const done = progress?.progress.cases_done ?? 0;
  const total = progress?.progress.total ?? run.nCases;
  const pct = total > 0 ? done / total : 0;

  // Counts down from the elapsed rate rather than a fixed estimate, so a slow
  // run says so instead of sitting at "3 seconds remaining" for a minute.
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed((Date.now() - started) / 1000), 500);
    return () => clearInterval(timer);
  }, [run.batchId]);

  const remaining = done > 0 ? Math.max(0, (elapsed / done) * (total - done)) : null;

  return (
    <section className="space-y-4 rounded-lg border border-hairline p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-medium text-ink">
          <Spinner className="size-3.5" />
          Running {total.toLocaleString("en-IN")} cases
        </h2>
        <span className="font-mono text-xs tabular-nums text-ink-muted">
          {done.toLocaleString("en-IN")} / {total.toLocaleString("en-IN")}
          {remaining !== null ? ` · about ${Math.ceil(remaining)}s left` : null}
        </span>
      </div>

      <div
        className="h-1.5 overflow-hidden rounded-full bg-subtle"
        role="progressbar"
        aria-valuenow={Math.round(pct * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Batch simulation progress"
      >
        <div
          className="h-full rounded-full bg-brand transition-[width] duration-300 ease-out"
          style={{ width: `${Math.max(2, pct * 100)}%` }}
        />
      </div>

      {progress && progress.time_series.length > 0 ? (
        <BatchLearningCurve
          series={progress.time_series}
          totalCases={total}
          live
        />
      ) : (
        <p className="py-8 text-center text-xs text-ink-faint">
          Waiting for the first window of results…
        </p>
      )}

      {progress?.current_bandit_rate != null ? (
        <p className="text-xs text-ink-muted">
          Latest window — bandit{" "}
          <strong className="font-mono font-medium text-ink">
            {formatPercent(progress.current_bandit_rate)}
          </strong>
          , fixed rule{" "}
          <strong className="font-mono font-medium text-ink">
            {formatPercent(progress.current_baseline_rate ?? 0)}
          </strong>
          .
        </p>
      ) : null}
    </section>
  );
}

export function BatchRunner({ initial }: { initial: BatchRun | null }) {
  const { run, follow } = useBatchRun(initial);
  const [starting, setStarting] = useState(false);

  async function begin() {
    setStarting(true);
    try {
      const started = await startBatch(DEFAULT_CASES);
      // Fetch the row rather than synthesising one: the server owns
      // `startedAt` and `nCases`, and a locally invented shape would differ
      // from what the next Realtime update replaces it with.
      follow(await fetchBatch(started.batchId));
    } catch (error) {
      toast.error("Could not start the batch", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setStarting(false);
    }
  }

  const running = run?.status === "running";
  const failed = run?.status === "failed";
  const completed = run && isComplete(run.result) ? run.result : null;

  if (!run) {
    return (
      <EmptyState
        icon={PlayCircle}
        title="No batch run yet"
        body="Simulates 1,000 recovery cases across all four playbooks, comparing the contextual bandit against the rule-based baseline on the same customers. Takes a few seconds."
        action={
          <Button onClick={begin} disabled={starting}>
            {starting ? <Spinner className="size-3.5" /> : <Play size={14} />}
            Run batch simulation
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      {failed ? (
        <div className="flex items-start gap-2.5 rounded-lg border border-danger/30 bg-danger-subtle p-4 text-danger">
          <TriangleAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
          <div>
            <p className="text-sm font-medium">The batch run failed</p>
            <p className="mt-0.5 text-xs opacity-90">{run.error ?? "No reason recorded."}</p>
          </div>
        </div>
      ) : null}

      {running ? <ProgressPanel run={run} /> : null}

      {completed ? (
        <>
          <section className="space-y-4 rounded-lg border border-hairline p-5">
            <div>
              <h2 className="text-sm font-medium text-ink">
                Bandit vs rule-based baseline —{" "}
                {completed.total_cases.toLocaleString("en-IN")} cases
              </h2>
              <p className="mt-1 max-w-2xl text-xs leading-relaxed text-ink-muted">
                Both policies decided the same customers, so the gap between the lines is the
                choice of arm and nothing else. The bandit trails early because exploration
                costs real recoveries — a policy that started ahead would be one that never had
                to learn anything.
              </p>
            </div>
            <BatchLearningCurve
              series={completed.time_series}
              totalCases={completed.total_cases}
              convergenceCase={completed.bandit_convergence_case}
            />
          </section>

          <BatchResultsSummary result={completed} startedAt={run.startedAt} />
        </>
      ) : null}

      {!running ? (
        <div className="flex justify-end">
          <Button variant="outline" onClick={begin} disabled={starting}>
            {starting ? <Spinner className="size-3.5" /> : <RotateCw size={14} />}
            Run new batch
          </Button>
        </div>
      ) : null}
    </div>
  );
}
