import type { Metadata } from "next";
import Link from "next/link";

import { CaseStatusBadge } from "@/components/domain/CaseStatusBadge";
import { PlaybookBadge } from "@/components/domain/PlaybookBadge";
import { FirstTimeDashboard } from "@/components/empty-states/FirstTimeDashboard";
import { PageHeader } from "@/components/shell/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import type { CaseListItem, Overview } from "@/lib/api/cases";
import { getCases, getOverview } from "@/lib/api/cases.server";
import { formatINR, formatPercent } from "@/lib/utils/format";

export const metadata: Metadata = { title: "Dashboard" };

/**
 * The home ticker.
 *
 * A merchant with no cases gets the onboarding state rather than a wall of
 * zeroes: four ₹0 tiles look like a broken product, not an idle one. The same
 * fallback covers an unreachable API, because a dashboard that invents zeroes
 * when it cannot reach the backend is worse than one that admits it has nothing
 * to show.
 */
export default async function DashboardPage() {
  let overview: Overview | null = null;
  let recentCases: CaseListItem[] = [];

  try {
    const [overviewResult, casesResult] = await Promise.all([getOverview(), getCases({ limit: 5 })]);
    overview = overviewResult;
    recentCases = casesResult.cases;
  } catch {
    overview = null;
  }

  if (!overview || recentCases.length === 0) {
    return (
      <>
        <PageHeader title="Dashboard" subtitle="Live view of recovery activity" />
        <FirstTimeDashboard />
      </>
    );
  }

  const kpis = [
    {
      label: "At Risk Today",
      value: formatINR(overview.amount_at_risk_today_cents),
      className: "text-warning",
      surface: "bg-warning-subtle",
    },
    {
      label: "Recovered Today",
      value: formatINR(overview.amount_recovered_today_cents),
      className: "text-success",
      surface: "bg-success-subtle",
    },
    {
      label: "Cases In Flight",
      value: String(overview.cases_in_flight),
      className: "text-info",
      surface: "bg-info-subtle",
    },
    {
      label: "Recovery Rate",
      value: formatPercent(overview.recovery_rate_today),
      className: "text-brand",
      surface: "bg-brand-subtle",
    },
  ];

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Live view of recovery activity" />

      <div className="mt-6 grid grid-cols-4 gap-4">
        {kpis.map((kpi) => (
          <Card key={kpi.label} className={`border-hairline ${kpi.surface}`}>
            <CardContent className="py-4">
              <div className="mb-1 text-xs text-ink-faint">{kpi.label}</div>
              <div
                className={`font-display text-3xl font-semibold tracking-tight ${kpi.className}`}
              >
                {kpi.value}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-muted">Recent Cases</h2>
          <Link href="/app/cases" className="text-xs text-brand hover:underline">
            View all →
          </Link>
        </div>
        <div className="divide-y divide-hairline overflow-hidden rounded-xl border border-hairline bg-elevated">
          {recentCases.map((row) => (
            <Link
              key={row.id}
              href={`/app/cases/${row.id}`}
              className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-subtle"
            >
              <CaseStatusBadge status={row.status} />
              <span className="flex-1 truncate text-sm font-medium text-ink">
                {row.customers?.name ?? "Unknown customer"}
              </span>
              <PlaybookBadge playbook={row.playbook} />
              <span className="font-mono text-sm text-ink-muted">
                {formatINR(row.amount_at_risk_cents)}
              </span>
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}
