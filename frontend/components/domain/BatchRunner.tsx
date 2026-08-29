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
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress, ProgressIndicator, ProgressTrack } from "@/components/ui/progress";
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
    // The `dark` class rather than a hand-picked set of dark colours. Every
    // token inside — including the Recharts axes, grid and tooltip, which read
    // `--text-tertiary` and `--border-subtle` — flips to the dark palette in one
    // move, so the live panel becomes a dark island on a light page with no
    // second colour scheme to keep in agreement. In dark mode it simply reads as
    // continuous with the page, which is correct: the panel is not trying to be
    // dark, it is trying to be *the thing currently happening*.
    <section className="dark space-y-4 rounded-none border border-hairline bg-base p-5 text-ink">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="flex items-center gap-2.5 font-display text-lg font-semibold tracking-[-0.01em] text-ink">
          {/* A pulsing dot rather than a spinner. A spinner says "waiting"; a
              live indicator says "this is moving", which is the true statement
              — the numbers underneath are changing while it is on screen. */}
          <span aria-hidden className="flex size-2 shrink-0">
            <span className="size-2 animate-pulse rounded-none bg-success" />
          </span>
          Running {total.toLocaleString("en-IN")} cases
        </h2>
        <span className="font-mono text-xs text-ink-muted tabular-nums">
          {done.toLocaleString("en-IN")} / {total.toLocaleString("en-IN")}
          {remaining !== null ? ` · about ${Math.ceil(remaining)}s left` : null}
        </span>
      </div>

      <Progress
        value={Math.round(pct * 100)}
        className="block"
        aria-label="Batch simulation progress"
      >
        <ProgressTrack className="h-1.5 bg-subtle">
          <ProgressIndicator className="rounded-none bg-brand" />
        </ProgressTrack>
      </Progress>

      {progress && progress.time_series.length > 0 ? (
        <BatchLearningCurve series={progress.time_series} totalCases={total} live />
      ) : (
        // Skeleton rather than a spinner: the shape of what is coming is more
        // informative than the fact that something is, and it holds the panel's
        // height so the page does not jump when the first window lands.
        <div className="space-y-2 py-2">
          <Skeleton className="h-[280px] w-full" />
          <Skeleton className="h-3 w-48" />
        </div>
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
            <Play aria-hidden />
            {starting ? "Starting…" : "Run batch simulation"}
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      {failed ? (
        <Alert variant="destructive" className="rounded-none border-danger/30 bg-danger-subtle">
          <TriangleAlert aria-hidden />
          <AlertTitle>The batch run failed</AlertTitle>
          <AlertDescription className="text-xs text-current opacity-90">
            {run.error ?? "No reason recorded."}
          </AlertDescription>
        </Alert>
      ) : null}

      {running ? <ProgressPanel run={run} /> : null}

      {completed ? (
        <>
          <section className="space-y-4 rounded-none border border-hairline bg-elevated p-5 shadow-card">
            <div>
              <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
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
            <RotateCw aria-hidden />
            {starting ? "Starting…" : "Run new batch"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
