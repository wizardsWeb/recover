import type { Metadata } from "next";

import { NetworkAlertBanner } from "@/components/domain/NetworkAlertBanner";
import { NetworkBenchmark } from "@/components/domain/NetworkBenchmark";
import { NetworkHeatmap } from "@/components/domain/NetworkHeatmap";
import { NetworkSimulatorControls } from "@/components/domain/NetworkSimulatorControls";
import { PageHeader } from "@/components/shell/PageHeader";
import { getAlerts, getBenchmark, getHeatmap } from "@/lib/api/network.server";
import { isLocal } from "@/lib/env";

export const metadata: Metadata = { title: "Network" };

/**
 * What every merchant's retries add up to.
 *
 * The page is arranged by urgency rather than by data model: an active outage
 * is something to act on now, the heatmap is something to plan around, and the
 * benchmark is something to think about this quarter.
 *
 * The three reads are issued together. Sequentially they would serialise three
 * round trips to the API for panels that do not depend on each other, and the
 * banner — the one that matters most — would be last to arrive.
 */
export default async function NetworkPage() {
  const [alerts, heatmap, benchmark] = await Promise.all([
    getAlerts(),
    getHeatmap(),
    getBenchmark(),
  ]);

  return (
    <>
      <PageHeader
        title="Network"
        subtitle="Bank and method health, pooled across every merchant"
      />

      <div className="space-y-6">
        <NetworkAlertBanner initial={alerts} />
        <NetworkHeatmap initial={heatmap} />
        <NetworkBenchmark data={benchmark} />
        {isLocal ? <NetworkSimulatorControls /> : null}
      </div>
    </>
  );
}
