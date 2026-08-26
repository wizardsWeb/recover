import type { Metadata } from "next";
import { RadioTower } from "lucide-react";

import { ComingSoon } from "@/components/empty-states/ComingSoon";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata: Metadata = { title: "Network" };

export default function NetworkPage() {
  return (
    <>
      <PageHeader title="Network" subtitle="Bank and method health across merchants" />
      <ComingSoon
        icon={RadioTower}
        phase="Phase 10"
        description="Aggregated success rates across the network reveal a gateway or bank going down before your own volume is enough to prove it."
      />
    </>
  );
}
