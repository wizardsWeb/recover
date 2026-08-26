import type { Metadata } from "next";
import { FolderOpen } from "lucide-react";

import { ComingSoon } from "@/components/empty-states/ComingSoon";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata: Metadata = { title: "Cases" };

export default function CasesPage() {
  return (
    <>
      <PageHeader title="Cases" subtitle="Every recovery the agent is working" />
      <ComingSoon
        icon={FolderOpen}
        phase="Phase 4"
        description="Once the agent core loop is running, every detected leak opens a case here — with its diagnosis, the actions taken, and what the customer said back."
      />
    </>
  );
}
