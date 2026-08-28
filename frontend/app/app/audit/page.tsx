import type { Metadata } from "next";

import { AuditLogEntry } from "@/components/domain/AuditLogEntry";
import { PageHeader } from "@/components/shell/PageHeader";
import { StaggeredItem } from "@/components/ui/StaggeredItem";
import type { AuditEvent } from "@/lib/api/cases";
import { getAuditEvents } from "@/lib/api/cases.server";

export const metadata: Metadata = { title: "Audit" };

/**
 * Every agent decision, execution and stop, newest first.
 *
 * Merchant-wide rather than per-case, because the question this page answers is
 * "what has the agent been doing" — and the answer a compliance reviewer needs
 * spans cases. The per-case view of the same rows is the timeline on the case
 * detail page.
 */
export default async function AuditPage() {
  let events: AuditEvent[] = [];
  let failed = false;
  try {
    events = (await getAuditEvents(100)).audit_events;
  } catch {
    failed = true;
  }

  return (
    <>
      <PageHeader
        title="Audit Log"
        subtitle="Every agent decision, execution, and stop — fully traceable"
      />
      <div className="mt-6 overflow-hidden rounded-xl border border-hairline bg-elevated">
        {failed ? (
          <div className="py-12 text-center text-sm text-ink-muted">
            Could not load the audit trail. The API did not respond.
          </div>
        ) : events.length === 0 ? (
          <div className="py-12 text-center text-sm text-ink-faint">
            No audit events yet. Fire a scenario to see the agent in action.
          </div>
        ) : (
          <div className="divide-y divide-hairline">
            {events.map((entry, index) => (
              <StaggeredItem key={entry.id} index={index} stagger={0.04}>
                <AuditLogEntry entry={entry} />
              </StaggeredItem>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
