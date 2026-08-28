"use client";

import { useCallback, useState } from "react";

import { PageHeader } from "@/components/shell/PageHeader";
import { AnimatedINR, AnimatedNumber, AnimatedPercent } from "@/components/ui/AnimatedNumber";
import { Card, CardContent } from "@/components/ui/card";
import { fetchOverview, type Overview } from "@/lib/api/cases";
import { useRealtimeCases, type RealtimeStatus } from "@/lib/hooks/useRealtimeCases";

const TILES = [
  {
    label: "At Risk Today",
    kind: "inr",
    read: (o: Overview) => o.amount_at_risk_today_cents,
    className: "text-warning",
    surface: "bg-warning-subtle",
  },
  {
    label: "Recovered Today",
    kind: "inr",
    read: (o: Overview) => o.amount_recovered_today_cents,
    className: "text-success",
    surface: "bg-success-subtle",
  },
  {
    label: "Cases In Flight",
    kind: "count",
    read: (o: Overview) => o.cases_in_flight,
    className: "text-info",
    surface: "bg-info-subtle",
  },
  {
    label: "Recovery Rate",
    kind: "percent",
    read: (o: Overview) => o.recovery_rate_today,
    className: "text-brand",
    surface: "bg-brand-subtle",
  },
] as const;

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
    <span
      className="inline-flex items-center gap-1.5 text-xs"
      title={live ? "Live — updating as cases change" : "Not connected — showing the last reading"}
    >
      <span
        aria-hidden
        className={`inline-block size-2 rounded-full ${
          live ? "animate-pulse bg-success" : "bg-ink-faint"
        }`}
      />
      <span className="sr-only">{live ? "Live updates connected" : "Live updates disconnected"}</span>
    </span>
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

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-4">
        {TILES.map((tile) => {
          const value = tile.read(overview);
          return (
            <Card key={tile.label} className={`border-hairline ${tile.surface}`}>
              <CardContent className="py-4">
                <div className="mb-1 text-xs text-ink-faint">{tile.label}</div>
                <div
                  className={`font-display text-3xl font-semibold tracking-tight ${tile.className}`}
                >
                  {tile.kind === "inr" ? (
                    <AnimatedINR value={value} />
                  ) : tile.kind === "percent" ? (
                    <AnimatedPercent value={value} />
                  ) : (
                    <AnimatedNumber value={value} />
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </>
  );
}
