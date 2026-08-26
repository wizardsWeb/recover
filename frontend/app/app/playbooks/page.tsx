import type { Metadata } from "next";
import { ListChecks } from "lucide-react";

import { ComingSoon } from "@/components/empty-states/ComingSoon";
import { PageHeader } from "@/components/shell/PageHeader";

export const metadata: Metadata = { title: "Playbooks" };

export default function PlaybooksPage() {
  return (
    <>
      <PageHeader title="Playbooks" subtitle="How the agent responds to each kind of leak" />
      <ComingSoon
        icon={ListChecks}
        phase="Phase 7"
        description="Failed payments, abandoned checkouts, broken subscription mandates, and overdue B2B invoices each get a playbook you can tune and pause."
      />
    </>
  );
}
