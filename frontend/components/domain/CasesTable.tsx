import Link from "next/link";

import { CaseStatusBadge } from "@/components/domain/CaseStatusBadge";
import { PlaybookBadge } from "@/components/domain/PlaybookBadge";
import { PersonAvatar } from "@/components/ui/PersonAvatar";
import { StaggerItem, StaggerList } from "@/components/ui/StaggerList";
import { Table, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { CaseListItem } from "@/lib/api/cases";
import { formatINR, formatRelativeTime } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

/**
 * The case list, in one place.
 *
 * The dashboard's five most recent rows and the cases page's full list are the
 * same table with a different number of rows in it, so they are the same
 * component. Two tables that only *look* alike is how a status colour gets
 * fixed on one screen and not the other.
 *
 * Rows are links, drawn as a stretched pseudo-element over the whole row rather
 * than as a `<Link>` wrapping every cell. A row of anchors is a row a keyboard
 * user has to tab through six times to get past; one anchor with an overlay is
 * one tab stop, keeps the table markup a table, and still gives the merchant
 * the entire row as a target.
 */
export function CasesTable({
  cases,
  className,
}: {
  cases: readonly CaseListItem[];
  className?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-card border border-hairline bg-elevated shadow-card",
        className,
      )}
    >
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {["Status", "Customer", "Playbook", "At risk", "Opened"].map((heading, index) => (
              <TableHead
                key={heading}
                className={cn(
                  "px-4 text-[11px] font-medium tracking-[0.06em] text-ink-faint uppercase",
                  // The money column is the only one a reader scans vertically
                  // to compare, and comparing right-aligned figures is the
                  // whole reason tabular numerals exist.
                  index === 3 && "text-right",
                )}
              >
                {heading}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>

        <StaggerList as="tbody" stagger={0.04}>
          {cases.map((row) => {
            const name = row.customers?.name ?? "Unknown customer";
            const email = row.customers?.email ?? "";
            return (
              <StaggerItem
                key={row.id}
                as="tr"
                className="relative border-b border-hairline transition-colors duration-150 last:border-b-0 hover:bg-brand-subtle"
              >
                <TableCell className="px-4 py-3">
                  <CaseStatusBadge status={row.status} />
                </TableCell>

                <TableCell className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <PersonAvatar seed={email || name} name={name} />
                    <div className="min-w-0">
                      {/* The one anchor. `after:absolute inset-0` stretches it
                          over the row; the row is `relative` for that reason. */}
                      <Link
                        href={`/app/cases/${row.id}`}
                        className="block truncate text-sm font-medium text-ink after:absolute after:inset-0 after:content-[''] focus-visible:underline focus-visible:outline-none"
                      >
                        {name}
                      </Link>
                      {email ? (
                        <span className="block truncate font-mono text-[11px] text-ink-faint">
                          {email}
                        </span>
                      ) : null}
                    </div>
                  </div>
                </TableCell>

                <TableCell className="px-4 py-3">
                  <PlaybookBadge playbook={row.playbook} />
                </TableCell>

                <TableCell className="px-4 py-3 text-right font-mono text-sm text-ink tabular-nums">
                  {formatINR(row.amount_at_risk_cents)}
                </TableCell>

                <TableCell className="px-4 py-3 font-mono text-[13px] text-ink-muted">
                  {formatRelativeTime(row.opened_at)}
                </TableCell>
              </StaggerItem>
            );
          })}
        </StaggerList>
      </Table>
    </div>
  );
}
