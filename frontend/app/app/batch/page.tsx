import type { Metadata } from "next";

import { BatchRunner } from "@/components/domain/BatchRunner";
import { PageHeader } from "@/components/shell/PageHeader";
import { getLatestBatch } from "@/lib/api/batch.server";

export const metadata: Metadata = { title: "Batch" };

/**
 * A thousand cases, both policies, one chart.
 *
 * The most recent run is fetched on the server so a completed one is in the
 * first HTML — this is the page someone screenshots, and a chart that arrives
 * after hydration is one that can be captured empty. Everything after that is
 * the client's: a run in flight is followed over Realtime.
 */
export default async function BatchPage() {
  const latest = await getLatestBatch();

  return (
    <>
      <PageHeader
        title="Batch"
        subtitle="A contextual bandit against a fixed rule, over the same thousand customers"
      />
      <BatchRunner initial={latest} />
    </>
  );
}
