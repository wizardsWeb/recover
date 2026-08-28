import type { Metadata } from "next";
import { TrendingUp } from "lucide-react";

import { RoiHero } from "@/components/domain/RoiHero";
import { RoiMethodology } from "@/components/domain/RoiMethodology";
import { SeedUpliftButton } from "@/components/domain/SeedUpliftButton";
import { UpliftBucketGrid } from "@/components/domain/UpliftBucketGrid";
import { EmptyState } from "@/components/empty-states/EmptyState";
import { PageHeader } from "@/components/shell/PageHeader";
import { getUpliftRoi } from "@/lib/api/roi.server";
import { isLocal } from "@/lib/env";

export const metadata: Metadata = { title: "ROI" };

/**
 * What the agent earned, and what it merely witnessed.
 *
 * The page is deliberately not a chart. There are two numbers that matter and
 * one relationship between them, and a chart would spend the reader's attention
 * on decoding an axis before they got to it.
 *
 * Rendered on the server so the figures are in the first HTML — this is the
 * page a merchant screenshots, and a money number that arrives after hydration
 * is one that can be screenshotted mid-count.
 */
export default async function ROIPage() {
  const roi = await getUpliftRoi();
  const hasHistory = roi.holdout_stats.treated_cases > 0;

  return (
    <>
      <PageHeader
        title="ROI"
        subtitle="What the agent earned, measured against holdouts"
        actions={isLocal ? <SeedUpliftButton /> : undefined}
      />

      {hasHistory ? (
        <div className="space-y-6">
          <RoiHero roi={roi} />

          {roi.bucket_breakdown.length > 0 ? (
            <section>
              <h2 className="mb-3 text-sm font-medium text-ink">Where the lift came from</h2>
              <UpliftBucketGrid rows={roi.bucket_breakdown} />
            </section>
          ) : null}

          <RoiMethodology note={roi.methodology_note} stats={roi.holdout_stats} />
        </div>
      ) : (
        <EmptyState
          icon={TrendingUp}
          title="Nothing to attribute yet"
          body="Once cases start closing, this page compares what the agent recovered against a holdout group it deliberately left alone — so the number here is what it caused, not just what arrived afterwards."
          action={isLocal ? <SeedUpliftButton /> : undefined}
        />
      )}
    </>
  );
}
