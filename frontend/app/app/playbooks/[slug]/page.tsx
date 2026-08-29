import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Clock, IndianRupee, Layers, Percent } from "lucide-react";

import { CasesTable } from "@/components/domain/CasesTable";
import { KpiCard } from "@/components/domain/KpiCard";
import { PlaybookEmptyArms } from "@/components/empty-states/PlaybookEmptyArms";
import { PageHeader } from "@/components/shell/PageHeader";
import { Badge } from "@/components/ui/badge";
import { StaggerList } from "@/components/ui/StaggerList";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { BanditArmPosterior, PlaybookDetail } from "@/lib/api/playbooks";
import { getBanditPosteriors, getPlaybook } from "@/lib/api/playbooks.server";

export const metadata: Metadata = { title: "Playbook" };

function armLabel(arm: string): string {
  return arm.replace(/_/g, " ");
}

/**
 * One arm's posterior, with the interval drawn as a band and the mean as a tick.
 *
 * The band is the point. An arm at 100% over two pulls and an arm at 71% over
 * forty are not comparable, and a bare percentage column invites exactly that
 * comparison — the width of the interval is the only thing on the row that says
 * how much the number can be trusted.
 */
function ArmRow({ arm }: { arm: BanditArmPosterior }) {
  const cold = arm.n_pulls === 0;
  const mean = Math.round(arm.expected_win_rate * 100);
  const low = Math.round(arm.ci_low * 100);
  const high = Math.round(arm.ci_high * 100);

  return (
    <TableRow className="border-hairline">
      <TableCell className="px-3 py-2">
        <span className={cold ? "text-xs text-ink-faint italic" : "text-xs text-ink"}>
          {armLabel(arm.arm_name)}
        </span>
      </TableCell>
      <TableCell className="w-[180px] px-3 py-2">
        <div className="relative h-1.5 w-full rounded-none bg-inset">
          {!cold ? (
            <>
              <div
                className="absolute h-full rounded-none bg-brand/25"
                style={{ left: `${low}%`, width: `${Math.max(high - low, 1)}%` }}
              />
              <div
                className="absolute h-full w-0.5 rounded-none bg-brand"
                style={{ left: `${mean}%` }}
              />
            </>
          ) : null}
        </div>
      </TableCell>
      <TableCell className="px-3 py-2 text-right font-mono text-xs tabular-nums">
        {cold ? <span className="text-ink-faint italic">Cold start</span> : `${mean}%`}
      </TableCell>
      <TableCell className="px-3 py-2 text-right font-mono text-xs text-ink-muted tabular-nums">
        {arm.n_pulls}
      </TableCell>
      <TableCell className="px-3 py-2 text-right font-mono text-[10px] text-ink-faint tabular-nums">
        {cold ? "—" : `${low}–${high}%`}
      </TableCell>
    </TableRow>
  );
}

const ARM_COLUMNS = [
  { label: "Arm", align: "left" as const },
  { label: "Win rate", align: "left" as const },
  { label: "Mean", align: "right" as const },
  { label: "Pulls", align: "right" as const },
  { label: "95% CI", align: "right" as const },
];

export default async function PlaybookDetailPage({
  params,
}: PageProps<"/app/playbooks/[slug]">) {
  const { slug } = await params;

  let playbook: PlaybookDetail;
  try {
    playbook = await getPlaybook(slug);
  } catch {
    notFound();
  }

  // Posteriors across every context bucket for this playbook. Not filtered to
  // one bucket: a merchant reading this page wants "which arms work", and
  // picking a single bucket for them would silently answer a narrower question.
  const { arms } = await getBanditPosteriors(slug).catch(() => ({ arms: [] }));
  const { stats } = playbook;

  return (
    <>
      <PageHeader
        title={playbook.label}
        subtitle={playbook.description}
        actions={
          playbook.enabled ? (
            <Badge className="bg-success-subtle text-success">Active</Badge>
          ) : (
            <Badge className="bg-warning-subtle text-warning">Paused</Badge>
          )
        }
      />

      <StaggerList className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          staggered
          label="Total cases"
          value={stats.totalCases}
          kind="count"
          tone="info"
          icon={Layers}
        />
        <KpiCard
          staggered
          label="Recovery rate"
          value={stats.recoveryRate}
          kind="percent"
          tone="brand"
          icon={Percent}
          footnote={
            // A rate over zero cases is not 0% — it is unmeasured. The footnote
            // says which of the two this is rather than letting a bold 0%
            // imply a playbook that tried and failed.
            stats.totalCases > 0 ? `${stats.casesRecovered} recovered` : "no cases yet"
          }
        />
        <KpiCard
          staggered
          label="Avg hours to recovery"
          value={stats.avgHoursToRecovery ?? 0}
          kind="count"
          tone="success"
          icon={Clock}
          footnote={stats.avgHoursToRecovery == null ? "nothing recovered yet" : undefined}
        />
        <KpiCard
          staggered
          label="Cost per recovery"
          value={0}
          kind="inr"
          tone="warning"
          icon={IndianRupee}
          // Every send in this build is simulated. Showing a real-looking cost
          // would be the one number on the page that is invented.
          footnote="sends are simulated"
        />
      </StaggerList>

      <section className="mt-6 space-y-3 rounded-none border border-hairline bg-elevated p-5 shadow-card">
        <div>
          <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">Arms</h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            What the bandit has learned about each action, across every context.
            The band is the 95% interval; the tick is the mean.
          </p>
        </div>

        {arms.length > 0 ? (
          <div className="overflow-x-auto rounded-md border border-hairline">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  {ARM_COLUMNS.map((column) => (
                    <TableHead
                      key={column.label}
                      className={`px-3 text-[10px] font-medium tracking-[0.06em] text-ink-faint uppercase ${
                        column.align === "right" ? "text-right" : ""
                      }`}
                    >
                      {column.label}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {arms.map((arm) => (
                  <ArmRow key={`${arm.arm_name}:${arm.context_bucket}`} arm={arm} />
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <PlaybookEmptyArms />
        )}

        <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-hairline pt-3 text-[11px] text-ink-faint">
          <span>Default arm: <span className="font-mono">{playbook.config.default_arm}</span></span>
          <span>Max {playbook.config.max_messages_per_day}/day, {playbook.config.max_messages_per_week}/week</span>
          <span>Hard stop after {playbook.config.hard_stop_after_days} days</span>
          {playbook.config.max_discount_pct > 0 ? (
            <span>Discount cap {playbook.config.max_discount_pct}%</span>
          ) : (
            <span>No discounts</span>
          )}
          <span>Channels: {playbook.config.channels_allowed.join(", ")}</span>
        </div>
      </section>

      <section className="mt-6 space-y-3">
        <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
          Recent cases
        </h2>

        {playbook.recent_cases.length > 0 ? (
          // The same table as the cases page. A playbook's cases are cases, and
          // a second bespoke table here is a second place to fix a bug.
          <CasesTable cases={playbook.recent_cases} />
        ) : (
          <p className="rounded-none border border-hairline bg-elevated py-8 text-center text-xs text-ink-faint">
            No cases under this playbook yet.
          </p>
        )}
      </section>
    </>
  );
}
