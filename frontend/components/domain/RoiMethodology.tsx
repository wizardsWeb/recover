"use client";

/**
 * How the number was arrived at, folded away.
 *
 * Collapsed by default and open in print. The merchant reading the dashboard
 * wants the figure; the one forwarding it to a finance team needs to be able to
 * show the working, and a page printed with the method hidden is a claim with
 * no support attached.
 *
 * The note text comes from the API rather than being written here. It describes
 * the estimator the backend actually ran, so it belongs with the code that runs
 * it — a copy in the frontend would go stale silently the first time the
 * estimator changed.
 */

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { HoldoutStats } from "@/lib/api/roi";
import { formatINR, formatPercent } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

interface RoiMethodologyProps {
  note: string;
  stats: HoldoutStats;
}

function Row({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-hairline py-2 last:border-0">
      <div className="min-w-0">
        <div className="text-xs text-ink">{label}</div>
        {hint ? <div className="text-[11px] text-ink-faint">{hint}</div> : null}
      </div>
      <div className="shrink-0 font-mono text-xs tabular-nums text-ink-muted">{value}</div>
    </div>
  );
}

export function RoiMethodology({ note, stats }: RoiMethodologyProps) {
  const [open, setOpen] = useState(false);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border border-hairline">
      <CollapsibleTrigger className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left">
        <span className="text-sm font-medium text-ink">How this is measured</span>
        <ChevronDown
          size={16}
          aria-hidden
          className={cn(
            "shrink-0 text-ink-faint transition-transform print:hidden",
            open && "rotate-180",
          )}
        />
      </CollapsibleTrigger>

      {/* `print:block` overrides the collapsed state: a printed page has no
          way to expand a section, so the working travels with the claim. */}
      <CollapsibleContent className="print:block">
        <div className="border-t border-hairline px-4 py-3">
          <p className="max-w-2xl text-xs leading-relaxed text-ink-muted">{note}</p>

          <div className="mt-4">
            <h3 className="text-[10px] font-medium tracking-wide text-ink-faint uppercase">
              The control group
            </h3>
            <div className="mt-1">
              <Row
                label="Cases held out"
                value={String(stats.holdout_cases)}
                hint={`${formatPercent(stats.holdout_share)} of closed cases — never contacted`}
              />
              <Row
                label="Controls with a known outcome"
                value={String(stats.resolved_controls)}
                hint="Unresolved controls are excluded — they would read as failures to recover"
              />
              <Row
                label="Recovery rate, contacted"
                value={formatPercent(stats.treated_recovery_rate)}
                hint={`${stats.treated_cases} cases the agent worked`}
              />
              <Row
                label="Recovery rate, left alone"
                value={formatPercent(stats.control_recovery_rate)}
                hint={`${stats.control_recoveries} of ${stats.resolved_controls} controls recovered anyway`}
              />
              {stats.foregone_recovery_cents !== undefined ? (
                <Row
                  label="What the holdout cost"
                  value={formatINR(stats.foregone_recovery_cents)}
                  hint="Recoveries these cases would likely have produced had the agent worked them"
                />
              ) : null}
            </div>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
