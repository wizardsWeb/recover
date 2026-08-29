"use client";

import { Activity, AlertTriangle, Percent, Wallet, type LucideIcon } from "lucide-react";
import { useCallback, useState } from "react";

import { KpiCard, type KpiCardProps } from "@/components/domain/KpiCard";
import { PageHeader } from "@/components/shell/PageHeader";
import { StaggerList } from "@/components/ui/StaggerList";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { fetchOverview, type Overview } from "@/lib/api/cases";
import { useRealtimeCases, type RealtimeStatus } from "@/lib/hooks/useRealtimeCases";

const TILES: Array<{
  label: string;
  kind: KpiCardProps["kind"];
  tone: KpiCardProps["tone"];
  // The component, not a rendered element: these entries are declarations, and
  // the element is built at the call site below. KpiCardProps["icon"] is a
  // ReactNode now, which a declaration cannot satisfy and JSX cannot construct.
  icon: LucideIcon;
  read: (o: Overview) => number;
}> = [
  {
    label: "At risk today",
    kind: "inr",
    tone: "warning",
    icon: AlertTriangle,
    read: (o) => o.amount_at_risk_today_cents,
  },
  {
    label: "Recovered today",
    kind: "inr",
    tone: "success",
    icon: Wallet,
    read: (o) => o.amount_recovered_today_cents,
  },
  {
    label: "Cases in flight",
    kind: "count",
    tone: "info",
    icon: Activity,
    read: (o) => o.cases_in_flight,
  },
  {
    label: "Recovery rate",
    kind: "percent",
    tone: "brand",
    icon: Percent,
    read: (o) => o.recovery_rate_today,
  },
];

/**
 * The live connection indicator.
 *
 * Grey and still is a legitimate resting state, not a fault: the numbers on
 * screen were correct when they were fetched and remain the best available
 * reading. Nothing is surfaced as an error, because a merchant cannot act on a
 * dropped websocket and Supabase reconnects without help.
 */
function LiveDot({ status }: { status: RealtimeStatus }) {
  const live = status === "live";
  return (
    <Tooltip>
      <TooltipTrigger
        render={<span tabIndex={0} className="inline-flex items-center gap-1.5 rounded-none" />}
      >
        <span
          aria-hidden
          className={`inline-block size-2 rounded-none ${
            live ? "animate-pulse bg-success" : "bg-ink-faint"
          }`}
        />
        <span className="sr-only">
          {live ? "Live updates connected" : "Live updates disconnected"}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {live ? "Live — updating as cases change" : "Not connected — showing the last reading"}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * The four KPI tiles, kept current by Supabase Realtime.
 *
 * Seeded from a server-rendered `initial` so the first paint has real numbers
 * rather than zeroes waiting on a client fetch. A Realtime event triggers a
 * re-read of the overview endpoint instead of arithmetic on the changed row:
 * three of these four figures are aggregates the backend computes, and
 * recomputing them here would produce a second, quietly divergent definition of
 * "recovered today".
 *
 * A failed re-read keeps the previous numbers on screen. The alternative —
 * blanking or zeroing them — would tell a merchant their recoveries had
 * disappeared when in fact one request did.
 */
export function DashboardLiveTicker({ initial }: { initial: Overview }) {
  const [overview, setOverview] = useState<Overview>(initial);

  const refresh = useCallback(() => {
    void fetchOverview()
      .then(setOverview)
      .catch(() => {
        /* Keep the last good reading. */
      });
  }, []);

  const status = useRealtimeCases(refresh);

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={
          status === "live"
            ? "Live view of recovery activity"
            : "Recovery activity — reconnecting for live updates"
        }
        titleAdornment={<LiveDot status={status} />}
      />

      <StaggerList className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
        {TILES.map((tile) => (
          <KpiCard
            key={tile.label}
            staggered
            label={tile.label}
            value={tile.read(overview)}
            kind={tile.kind}
            tone={tile.tone}
            icon={<tile.icon strokeWidth={1.5} />}
          />
        ))}
      </StaggerList>
    </>
  );
}
