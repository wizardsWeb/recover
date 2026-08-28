import { ScrollText } from "lucide-react";

import { EmptyState } from "@/components/empty-states/EmptyState";

/** The audit trail before the agent has done anything. */
export function NoAuditEvents() {
  return (
    <EmptyState
      icon={ScrollText}
      title="No audit events yet"
      body="Every agent decision, execution, and stop is logged here. Fire a scenario to see the trail."
    />
  );
}
