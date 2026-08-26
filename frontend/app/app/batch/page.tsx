import type { Metadata } from "next";
import { PlaySquare } from "lucide-react";

import { ComingSoon } from "@/components/empty-states/ComingSoon";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata: Metadata = { title: "Batch" };

export default function BatchPage() {
  return (
    <>
      <PageHeader title="Batch" subtitle="Replay scenarios at volume" />
      <ComingSoon
        icon={PlaySquare}
        phase="Phase 11"
        description="Run a thousand simulated cases through the agent to watch the bandit's learning curve settle and compare arms."
      />
    </>
  );
}
