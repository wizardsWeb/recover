import Link from "next/link";

import { CaseStatusBadge } from "@/components/domain/CaseStatusBadge";
import { PlaybookBadge } from "@/components/domain/PlaybookBadge";
import { UpliftBucketBadge } from "@/components/domain/UpliftBucketBadge";
import { PersonAvatar } from "@/components/ui/PersonAvatar";
import { StaggerItem, StaggerList } from "@/components/ui/StaggerList";
import { Table, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { CaseListItem } from "@/lib/api/cases";
import { formatINR, formatRelativeTime } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

interface Column {
  key: string;
  label: string;
  align?: "right";
  /** Present only on the full list; the dashboard's five rows do without. */
  extended?: boolean;
}

const COLUMNS: Column[] = [
  { key: "status", label: "Status" },
  { key: "customer", label: "Customer" },
  { key: "playbook", label: "Playbook" },
  { key: "uplift", label: "Uplift", extended: true },
  { key: "at_risk", label: "At risk", align: "right" },
  { key: "recovered", label: "Recovered", align: "right", extended: true },
  { key: "opened", label: "Opened" },
  { key: "step", label: "Step", extended: true },
];

/**
 * The case list, in one place.
 *
 * The dashboard's five most recent rows and the cases page's full list are the
 * same table with three more columns on one of them, so they are the same
 * component. Two tables that only *look* alike is how a status colour gets
 * fixed on one screen and not the other.
 *
 * Rows are links, drawn as a stretched pseudo-element over the whole row rather
 * than as an anchor per cell. A row of anchors is a row a keyboard user tabs
 * through six times to get past; one anchor with an overlay is one tab stop and
 * still gives the merchant the entire row as a target. The `<tr>` carries the
 * `position: relative` that the overlay resolves against — supported in every
 * evergreen browser, and the reason the row markup stays a real table row
 * rather than a grid of divs pretending to be one.
 */
export function CasesTable({
  cases,
  variant = "recent",
  flashingIds,
  className,
}: {
  cases: readonly CaseListItem[];
  variant?: "recent" | "full";
  /** Ids that just arrived over Realtime, to be marked for a moment. */
  flashingIds?: ReadonlySet<string>;
  className?: string;
}) {
  const columns = COLUMNS.filter((column) => variant === "full" || !column.extended);

  return (
    <div
      className={cn(
        "overflow-x-auto rounded-none border border-hairline bg-elevated shadow-card",
        className,
      )}
    >
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((column) => (
              <TableHead
                key={column.key}
                className={cn(
                  "px-4 text-[11px] font-medium tracking-[0.06em] text-ink-faint uppercase",
                  // Money columns are the only ones a reader scans vertically to
                  // compare, and comparing right-aligned figures is the whole
                  // reason tabular numerals exist.
                  column.align === "right" && "text-right",
                )}
              >
                {column.label}
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
                className={cn(
                  "relative border-b border-hairline transition-colors duration-150 last:border-b-0 hover:bg-brand-subtle",
                  flashingIds?.has(row.id) && "animate-row-flash",
                )}
              >
                <TableCell className="px-4 py-3">
                  <CaseStatusBadge status={row.status} />
                </TableCell>

                <TableCell className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <PersonAvatar seed={email || name} name={name} />
                    <div className="min-w-0">
                      {/* The one anchor. `after:absolute inset-0` stretches it
                          over the row, which is why the row is `relative`. */}
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

                {variant === "full" && (
                  <TableCell className="px-4 py-3">
                    {/* Informational, never a control. The bucket explains what
                        the agent expected to change by acting; it does not gate
                        anything the merchant can do to this case. */}
                    <UpliftBucketBadge bucket={row.uplift_bucket} />
                  </TableCell>
                )}

                <TableCell className="px-4 py-3 text-right font-mono text-sm text-ink tabular-nums">
                  {formatINR(row.amount_at_risk_cents)}
                </TableCell>

                {variant === "full" && (
                  <TableCell
                    className={cn(
                      "px-4 py-3 text-right font-mono text-sm tabular-nums",
                      row.amount_recovered_cents > 0 ? "text-success" : "text-ink-faint",
                    )}
                  >
                    {row.amount_recovered_cents > 0
                      ? formatINR(row.amount_recovered_cents)
                      : "—"}
                  </TableCell>
                )}

                <TableCell className="px-4 py-3 font-mono text-[13px] text-ink-muted">
                  {formatRelativeTime(row.opened_at)}
                </TableCell>

                {variant === "full" && (
                  <TableCell className="px-4 py-3">
                    <span className="rounded-md bg-inset px-2 py-0.5 font-mono text-[11px] text-ink-faint">
                      {row.current_step ?? "—"}
                    </span>
                  </TableCell>
                )}
              </StaggerItem>
            );
          })}
        </StaggerList>
      </Table>
    </div>
  );
}
