"use client";

/**
 * What a thousand cases came to.
 *
 * Six figures, and the pairs matter more than any one of them: gross beside
 * incremental, and the settled recovery rate beside the whole-run one. Showing
 * either half alone is the standard way a recovery dashboard flatters itself —
 * gross without a counterfactual claims money that would have arrived anyway,
 * and a settled rate without the run average writes off the exploration that
 * paid for it.
 *
 * The compliance strip below is three zeros, and it is here rather than buried
 * in the audit log because zero is the claim a merchant is being asked to
 * trust. It is reported alongside the number of sends the guardrail actually
 * stopped: the zero on its own would hide the work, and the blocks on their own
 * would read as a fault rate.
 */

import Link from "next/link";
import { ArrowRight, CheckCircle2, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { Card, CardContent } from "@/components/ui/card";
import { LiftCard } from "@/components/ui/LiftCard";
import { StaggerList } from "@/components/ui/StaggerList";
import type { BatchResult } from "@/lib/api/batch";
import { formatPercent, formatRupees } from "@/lib/utils/format";

function Metric({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: ReactNode;
  note: string;
  tone?: string;
}) {
  return (
    <LiftCard staggered>
      <Card className="h-full border-hairline shadow-card">
        <CardContent className="p-5">
          <p className="text-[11px] font-medium tracking-[0.06em] text-ink-faint uppercase">
            {label}
          </p>
          <p
            className={`mt-1.5 font-display text-3xl leading-none font-bold tracking-[-0.03em] tabular-nums ${tone ?? "text-ink"}`}
          >
            {value}
          </p>
          <p className="mt-2 text-xs leading-relaxed text-ink-muted">{note}</p>
        </CardContent>
      </Card>
    </LiftCard>
  );
}

function ComplianceStat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div>
      <div className="flex items-baseline gap-2">
        {/* The zero is the claim. It is set in the display face at 24px and in
            the success colour because it is the number a merchant is being
            asked to trust, and rendering it at the same weight as the note
            beside it would bury the only structural guarantee on the page. */}
        <span className="font-display text-2xl leading-none font-bold text-success tabular-nums">
          {value}
        </span>
        <span className="text-xs text-ink">{label}</span>
      </div>
      <div className="mt-1 text-[11px] text-ink-muted">{note}</div>
    </div>
  );
}

export function BatchResultsSummary({
  result,
  startedAt,
}: {
  result: BatchResult;
  startedAt: string | null;
}) {
  const settled = result.settled_recovery_rate_by_policy.bandit ?? 0;
  const whole = result.recovery_rate_by_policy.bandit ?? 0;
  const baseline = result.settled_recovery_rate_by_policy.baseline ?? 0;
  const attribution =
    result.gross_recovered_inr > 0
      ? result.incremental_recovered_inr / result.gross_recovered_inr
      : 0;
  const compliance = result.compliance_summary;
  const blocks = compliance.rbi_blocks + compliance.trai_blocks;

  // The audit page, scoped to when this run happened.
  const auditHref = startedAt
    ? `/app/audit?since=${encodeURIComponent(startedAt)}`
    : "/app/audit";

  return (
    <div className="space-y-4">
      <StaggerList className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Metric
          label="Revenue at risk"
          value={formatRupees(result.total_at_risk_inr)}
          note={`Across ${result.total_cases.toLocaleString("en-IN")} cases in four playbooks.`}
        />
        <Metric
          label="Gross recovered"
          value={formatRupees(result.gross_recovered_inr)}
          note={`${formatPercent(settled)} settled recovery rate, ${formatPercent(whole)} including the exploration it cost to get there.`}
        />
        <Metric
          label="Incremental recovered"
          value={
            <AnimatedNumber
              value={result.incremental_recovered_inr}
              startOnView
              format={(n) => formatRupees(n)}
              className="text-brand"
            />
          }
          tone="text-brand"
          note={`${formatPercent(attribution)} of gross. The rest would have arrived without the agent.`}
        />
        <Metric
          label="RBI violations"
          value="0"
          tone="text-success"
          note={`Checked before every send, so none can reach the data. ${blocks} sends were stopped.`}
        />
        <Metric
          label="Opt-outs honoured"
          value={String(result.opt_outs_honored)}
          tone="text-success"
          note={`Contact stopped within ${compliance.avg_opt_out_response_seconds}s on average — a simulated constant.`}
        />
        <Metric
          label="Cost of recovery"
          value={`₹${result.cost_per_100_inr_recovered.toFixed(2)}`}
          note="Spent on messages and handoffs per ₹100 recovered."
        />
      </StaggerList>

      <section className="rounded-none border border-hairline bg-elevated p-5 shadow-card">
        <h3 className="flex items-center gap-2 font-display text-lg font-semibold tracking-[-0.01em] text-ink">
          <ShieldCheck className="size-4 text-success" strokeWidth={1.75} aria-hidden />
          Compliance
        </h3>

        <div className="mt-3 grid gap-4 sm:grid-cols-3">
          <ComplianceStat
            label="RBI mandate violations"
            value={String(compliance.rbi_violations)}
            note={`${compliance.rbi_blocks} retries stopped at the per-cycle ceiling`}
          />
          <ComplianceStat
            label="TRAI message violations"
            value={String(compliance.trai_violations)}
            note={`${compliance.trai_blocks} sends held outside the 9pm–9am window`}
          />
          <ComplianceStat
            label="Opt-outs honoured"
            value={String(compliance.opt_outs_honored)}
            note={`avg ${compliance.avg_opt_out_response_seconds}s to stop contact`}
          />
        </div>

        <p className="mt-3 flex items-start gap-1.5 border-t border-hairline pt-3 text-[11px] leading-relaxed text-ink-muted">
          <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-success" aria-hidden />
          <span>
            A violation is one that got past the guardrail. Every check runs before its send, so
            the zeros are structural rather than lucky — the {blocks} blocks beside them are the
            same mechanism working.
          </span>
        </p>

        <Link
          href={auditHref}
          className="mt-3 inline-flex items-center gap-1 text-xs text-brand hover:underline"
        >
          View audit trail
          <ArrowRight size={12} aria-hidden />
        </Link>
      </section>

      <p className="text-[11px] text-ink-faint">
        Baseline settled at {formatPercent(baseline)} over the same cases. Simulation completed in{" "}
        {result.elapsed_seconds}s.
      </p>
    </div>
  );
}
