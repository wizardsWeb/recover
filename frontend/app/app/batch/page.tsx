import type { Metadata } from "next";

import { BanditLearningCurve } from "@/components/domain/BanditLearningCurve";
import { PageHeader } from "@/components/shell/PageHeader";
import {
  BATCH_SUMMARY,
  CROSSOVER_AT_CASE,
  LIFT_PP,
} from "@/lib/data/bandit_curve_demo";

export const metadata: Metadata = { title: "Batch" };

/** Paise to a rupee figure in lakhs, the unit the numbers are quoted in. */
function lakhs(cents: number): string {
  return `₹${(cents / 100 / 100_000).toFixed(1)}L`;
}

function SummaryStat({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="space-y-1">
      <div className="text-xs text-ink-faint">{label}</div>
      <div className="font-mono text-2xl tabular-nums text-ink">{value}</div>
      <div className="text-xs text-ink-muted">{note}</div>
    </div>
  );
}

export default function BatchPage() {
  return (
    <>
      <PageHeader title="Batch" subtitle="Replay scenarios at volume" />

      <div className="space-y-6">
        <div className="rounded-lg border border-warning/40 bg-warning-subtle px-4 py-3 text-sm text-warning">
          <span className="font-medium">Pre-computed.</span> Full batch simulation
          lands in Phase 11 — this chart shows recorded convergence data, not a
          live run.
        </div>

        <section className="space-y-4 rounded-lg border border-hairline p-4">
          <div>
            <h2 className="text-sm font-medium text-ink">
              Learning curve — bandit vs fixed rule
            </h2>
            <p className="mt-1 text-xs text-ink-muted">
              The bandit loses for the first {CROSSOVER_AT_CASE} cases. That is
              exploration, and it costs real recoveries — a policy that started
              ahead would be one that never had to learn anything. It settles{" "}
              {LIFT_PP} percentage points above the fixed rule.
            </p>
          </div>

          <BanditLearningCurve />
        </section>

        <section className="grid gap-6 rounded-lg border border-hairline p-4 sm:grid-cols-3">
          <SummaryStat
            label="At risk"
            value={lakhs(BATCH_SUMMARY.atRiskCents)}
            note={`across ${BATCH_SUMMARY.casesSimulated.toLocaleString("en-IN")} simulated cases`}
          />
          <SummaryStat
            label="Gross recovered"
            value={lakhs(BATCH_SUMMARY.grossRecoveredCents)}
            note="everything that came back after the agent acted"
          />
          <SummaryStat
            label="Incremental"
            value={lakhs(BATCH_SUMMARY.incrementalRecoveredCents)}
            note="what would not have come back on its own — the honest number"
          />
        </section>
      </div>
    </>
  );
}
