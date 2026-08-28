import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CaseStatusBadge } from "@/components/domain/CaseStatusBadge";
import { PlaybookEmptyArms } from "@/components/empty-states/PlaybookEmptyArms";
import { PageHeader } from "@/components/shell/PageHeader";
import type { BanditArmPosterior, PlaybookDetail } from "@/lib/api/playbooks";
import { getBanditPosteriors, getPlaybook } from "@/lib/api/playbooks.server";
import { formatINR, formatRelativeTime } from "@/lib/utils/format";

export const metadata: Metadata = { title: "Playbook" };

function armLabel(arm: string): string {
  return arm.replace(/_/g, " ");
}

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div>
      <div className="text-[10px] tracking-wide text-ink-faint uppercase">{label}</div>
      <div className="mt-0.5 font-mono text-xl tabular-nums text-ink">{value}</div>
      {note ? <div className="text-[10px] text-ink-faint">{note}</div> : null}
    </div>
  );
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
    <tr className="border-b border-hairline/60">
      <td className="py-2 pr-3">
        <span className={`text-xs ${cold ? "text-ink-faint italic" : "text-ink"}`}>
          {armLabel(arm.arm_name)}
        </span>
      </td>
      <td className="w-[180px] py-2 pr-3">
        <div className="relative h-1.5 w-full rounded-4xl bg-inset">
          {!cold ? (
            <>
              <div
                className="absolute h-full rounded-4xl bg-brand/25"
                style={{ left: `${low}%`, width: `${Math.max(high - low, 1)}%` }}
              />
              <div
                className="absolute h-full w-0.5 rounded-4xl bg-brand"
                style={{ left: `${mean}%` }}
              />
            </>
          ) : null}
        </div>
      </td>
      <td className="py-2 pr-3 text-right font-mono text-xs tabular-nums">
        {cold ? <span className="text-ink-faint italic">Cold start</span> : `${mean}%`}
      </td>
      <td className="py-2 pr-3 text-right font-mono text-xs tabular-nums text-ink-muted">
        {arm.n_pulls}
      </td>
      <td className="py-2 text-right font-mono text-[10px] tabular-nums text-ink-faint">
        {cold ? "—" : `${low}–${high}%`}
      </td>
    </tr>
  );
}

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
            <span className="rounded-4xl bg-success-subtle px-2 py-0.5 text-xs font-medium text-success">
              Active
            </span>
          ) : (
            <span className="rounded-4xl bg-warning-subtle px-2 py-0.5 text-xs font-medium text-warning">
              Paused
            </span>
          )
        }
      />

      <section className="grid grid-cols-2 gap-6 rounded-lg border border-hairline p-4 sm:grid-cols-4">
        <Kpi label="Total cases" value={String(stats.totalCases)} />
        <Kpi
          label="Recovery rate"
          value={stats.totalCases > 0 ? `${Math.round(stats.recoveryRate * 100)}%` : "—"}
          note={stats.totalCases > 0 ? `${stats.casesRecovered} recovered` : "no cases yet"}
        />
        <Kpi
          label="Avg time to recovery"
          value={
            stats.avgHoursToRecovery != null ? `${stats.avgHoursToRecovery.toFixed(1)}h` : "—"
          }
        />
        <Kpi
          label="Cost per recovery"
          value="₹0"
          // Every send in this build is simulated. Showing a real-looking cost
          // would be the one number on the page that is invented.
          note="sends are simulated"
        />
      </section>

      <section className="mt-6 space-y-3 rounded-lg border border-hairline p-4">
        <div>
          <h2 className="text-sm font-medium text-ink">Arms</h2>
          <p className="mt-0.5 text-xs text-ink-muted">
            What the bandit has learned about each action, across every context.
            The band is the 95% interval; the tick is the mean.
          </p>
        </div>

        {arms.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-hairline text-[10px] tracking-wide text-ink-faint uppercase">
                  <th scope="col" className="pb-2 text-left font-medium">Arm</th>
                  <th scope="col" className="pb-2 text-left font-medium">Win rate</th>
                  <th scope="col" className="pb-2 text-right font-medium">Mean</th>
                  <th scope="col" className="pb-2 text-right font-medium">Pulls</th>
                  <th scope="col" className="pb-2 text-right font-medium">95% CI</th>
                </tr>
              </thead>
              <tbody>
                {arms.map((arm) => (
                  <ArmRow key={`${arm.arm_name}:${arm.context_bucket}`} arm={arm} />
                ))}
              </tbody>
            </table>
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

      <section className="mt-6 space-y-3 rounded-lg border border-hairline p-4">
        <h2 className="text-sm font-medium text-ink">Recent cases</h2>

        {playbook.recent_cases.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-hairline text-[10px] tracking-wide text-ink-faint uppercase">
                  <th scope="col" className="pb-2 text-left font-medium">Customer</th>
                  <th scope="col" className="pb-2 text-left font-medium">Status</th>
                  <th scope="col" className="pb-2 text-right font-medium">At risk</th>
                  <th scope="col" className="pb-2 text-right font-medium">Opened</th>
                </tr>
              </thead>
              <tbody>
                {playbook.recent_cases.map((row) => (
                  <tr key={row.id} className="border-b border-hairline/60">
                    <td className="py-2">
                      <Link
                        href={`/app/cases/${row.id}`}
                        className="text-ink transition-colors hover:text-brand"
                      >
                        {row.customers?.name ?? "Unknown"}
                      </Link>
                    </td>
                    <td className="py-2">
                      <CaseStatusBadge status={row.status} />
                    </td>
                    <td className="py-2 text-right font-mono tabular-nums text-ink-muted">
                      {formatINR(row.amount_at_risk_cents)}
                    </td>
                    <td className="py-2 text-right text-ink-faint">
                      {formatRelativeTime(row.opened_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-4 text-center text-xs text-ink-faint">
            No cases under this playbook yet.
          </p>
        )}
      </section>
    </>
  );
}
