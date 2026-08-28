"use client";

/**
 * Loads the causal graph for a case and renders it, or explains its absence.
 *
 * Client-fetched rather than served with the page. React Flow and dagre are
 * around 150KB together and are needed by exactly one section of one route, so
 * they load when a reader is actually looking at a diagnosed case rather than
 * on every case-detail render.
 *
 * The section only mounts when `diagnosis.dag_traversal_used` is true, which the
 * page checks before rendering this at all. That is the honest condition: a case
 * closed before Phase 12 has no feature vector, and there is nothing to light
 * up — a graph with no path through it would suggest the agent considered these
 * hypotheses when it did not.
 */

import { useEffect, useState } from "react";
import { Network } from "lucide-react";

import { CausalDagViewer } from "@/components/domain/CausalDagViewer";
import { Skeleton } from "@/components/ui/skeleton";
import type { CaseDag } from "@/lib/api/dag";
import { fetchCaseDag } from "@/lib/api/dag";

function DagSkeleton() {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_240px]">
      <Skeleton className="h-[520px] w-full rounded-lg" />
      <div className="space-y-3">
        <Skeleton className="h-[104px] w-full rounded-lg" />
        {[0, 1, 2, 3, 4].map((row) => (
          <div key={row} className="space-y-1">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-1 w-full rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function CausalReasoningSection({ caseId }: { caseId: string }) {
  const [dag, setDag] = useState<CaseDag | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchCaseDag(caseId)
      .then((result) => {
        if (!cancelled) setDag(result);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  return (
    <section className="mt-6">
      <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold tracking-wider text-ink-muted uppercase">
        <Network size={14} aria-hidden />
        Causal Reasoning
      </h2>
      <p className="mb-4 max-w-2xl text-xs leading-relaxed text-ink-muted">
        The diagnosis came from this graph, not from a model&rsquo;s opinion. Facts the agent
        checked are on the left; the causes they rule in and out are on the right. The same
        evidence always produces the same answer.
      </p>

      {failed ? (
        <div className="rounded-lg border border-hairline py-10 text-center text-xs text-ink-muted">
          Could not load the causal graph.
        </div>
      ) : dag ? (
        <CausalDagViewer dag={dag} />
      ) : (
        <DagSkeleton />
      )}
    </section>
  );
}
