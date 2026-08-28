import type { Metadata } from "next";
import Link from "next/link";

import { AuditLogEntry } from "@/components/domain/AuditLogEntry";
import { NoAuditEvents } from "@/components/empty-states/NoAuditEvents";
import { PageHeader } from "@/components/shell/PageHeader";
import { StaggeredItem } from "@/components/ui/StaggeredItem";
import type { AuditEvent } from "@/lib/api/cases";
import { getAuditEvents } from "@/lib/api/cases.server";
import { formatDateTime } from "@/lib/utils/format";

export const metadata: Metadata = { title: "Audit" };

/**
 * Every agent decision, execution and stop, newest first.
 *
 * Merchant-wide rather than per-case, because the question this page answers is
 * "what has the agent been doing" — and the answer a compliance reviewer needs
 * spans cases. The per-case view of the same rows is the timeline on the case
 * detail page.
 *
 * `?since=` scopes it to a window. The batch results screen links here with the
 * run's start time, and the heading says so — a filtered log that looked
 * identical to an unfiltered one would have a reviewer draw conclusions about
 * the wrong period.
 */
export default async function AuditPage({ searchParams }: PageProps<"/app/audit">) {
  const { since } = await searchParams;
  const scopedTo = typeof since === "string" ? since : undefined;

  let events: AuditEvent[] = [];
  let failed = false;
  try {
    events = (await getAuditEvents(100, scopedTo)).audit_events;
  } catch {
    failed = true;
  }

  return (
    <>
      <PageHeader
        title="Audit Log"
        subtitle={
          scopedTo
            ? `Everything the agent did since ${formatDateTime(scopedTo)}`
            : "Every agent decision, execution, and stop — fully traceable"
        }
        actions={
          scopedTo ? (
            <Link
              href="/app/audit"
              className="text-xs text-brand hover:underline"
            >
              Clear filter
            </Link>
          ) : undefined
        }
      />
      <div className="mt-6 overflow-hidden rounded-xl border border-hairline bg-elevated">
        {failed ? (
          <div className="py-12 text-center text-sm text-ink-muted">
            Could not load the audit trail. The API did not respond.
          </div>
        ) : events.length === 0 ? (
          <NoAuditEvents />
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
