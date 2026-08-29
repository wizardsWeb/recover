import type { Metadata } from "next";
import Link from "next/link";

import { CasesTable } from "@/components/domain/CasesTable";
import { DashboardLiveTicker } from "@/components/domain/DashboardLiveTicker";
import { RecoveryFunnel } from "@/components/domain/RecoveryFunnel";
import { FirstTimeDashboard } from "@/components/empty-states/FirstTimeDashboard";
import { PageHeader } from "@/components/shell/PageHeader";
import type { CaseListItem, Overview } from "@/lib/api/cases";
import { getCases, getOverview } from "@/lib/api/cases.server";
import { funnelFrom } from "@/lib/domain/funnel";

export const metadata: Metadata = { title: "Dashboard" };

/**
 * How many cases the funnel is computed over.
 *
 * There is no funnel endpoint, so the stages are derived from case rows. 200 is
 * enough for the shape to be stable and small enough to stay one cheap request;
 * the funnel is labelled with what it covers so nobody reads it as all-time.
 */
const FUNNEL_WINDOW = 200;

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
  let funnelCases: CaseListItem[] = [];

  try {
    const [overviewResult, casesResult] = await Promise.all([
      getOverview(),
      getCases({ limit: FUNNEL_WINDOW }),
    ]);
    overview = overviewResult;
    funnelCases = casesResult.cases;
    recentCases = funnelCases.slice(0, 5);
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

  const stages = funnelFrom(funnelCases);

  return (
    <>
      {/* The tiles are seeded with server-fetched numbers and then kept current
          by Realtime, so the island owns the header too — the live dot
          qualifies the "Dashboard" heading and its status lives in the client. */}
      <DashboardLiveTicker initial={overview} />

      <section className="mt-8 rounded-card border border-hairline bg-elevated p-6 shadow-card">
        <div className="mb-6 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
            Recovery funnel
          </h2>
          <p className="text-xs text-ink-faint">
            Last {Math.min(funnelCases.length, FUNNEL_WINDOW)} cases · each stage counts every case
            that reached it
          </p>
        </div>
        <RecoveryFunnel stages={stages} />
      </section>

      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
            Recent cases
          </h2>
          <Link
            href="/app/cases"
            className="text-xs text-brand transition-colors hover:text-brand-hover hover:underline"
          >
            View all →
          </Link>
        </div>
        <CasesTable cases={recentCases} />
      </section>
    </>
  );
}
