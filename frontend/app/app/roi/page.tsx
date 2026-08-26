import type { Metadata } from "next";
import { TrendingUp } from "lucide-react";

import { ComingSoon } from "@/components/empty-states/ComingSoon";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata: Metadata = { title: "ROI" };

export default function ROIPage() {
  return (
    <>
      <PageHeader title="ROI" subtitle="What the agent earned, measured against holdouts" />
      <ComingSoon
        icon={TrendingUp}
        phase="Phase 9"
        description="A holdout group never gets contacted, so recovered revenue can be reported as uplift over doing nothing rather than as raw totals."
      />
    </>
  );
}
