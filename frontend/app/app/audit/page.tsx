import type { Metadata } from "next";
import { FileSearch } from "lucide-react";

import { ComingSoon } from "@/components/empty-states/ComingSoon";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata: Metadata = { title: "Audit" };

export default function AuditPage() {
  return (
    <>
      <PageHeader title="Audit" subtitle="Every decision, in order, with its reasoning" />
      <ComingSoon
        icon={FileSearch}
        phase="Phase 8"
        description="A full trail of what the agent saw, what it decided, why, and which guardrail checks it ran before acting."
      />
    </>
  );
}
