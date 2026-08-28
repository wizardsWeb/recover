"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useCallback, useRef, useState, type ReactNode } from "react";

import { CaseStatusBadge } from "@/components/domain/CaseStatusBadge";
import { PlaybookBadge } from "@/components/domain/PlaybookBadge";
import { PageHeader } from "@/components/shell/PageHeader";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchCases, type CaseListItem } from "@/lib/api/cases";
import { useRealtimeCases } from "@/lib/hooks/useRealtimeCases";
import { formatINR, formatRelativeTime } from "@/lib/utils/format";

const FLASH_MS = 1500;

/**
 * The cases table, kept current by Supabase Realtime.
 *
 * Seeded from the server render so the first paint is the real list, then
 * re-read on every change event. It re-reads rather than applying the Realtime
 * payload directly because that payload is a bare `recovery_cases` row — the
 * customer name this table renders in its second column is not in it, and a row
 * that appeared saying "—" where a name belongs would look like data loss.
 *
 * New ids are tracked so an arriving row can announce itself, and are cleared
 * on a timer. Without the clear, every row that ever arrived would still be
 * marked, and a later re-render would replay the flash on all of them at once.
 */
export function CasesRealtimeUpdater({
  initial,
  emptyState,
}: {
  initial: CaseListItem[];
  /**
   * Rendered while the list is empty.
   *
   * Passed in from the server component rather than decided here so the empty
   * state can stay a server component, and so this island owns *when* it shows
   * rather than what it says. It has to live inside the island: a merchant who
   * opens an empty Cases page and then fires a scenario needs the table to
   * replace this, and an empty state rendered by the server would sit there
   * unchanged while rows arrived underneath it.
   */
  emptyState: ReactNode;
}) {
  const [cases, setCases] = useState<CaseListItem[]>(initial);
  const [flashing, setFlashing] = useState<Set<string>>(new Set());
  const knownIds = useRef<Set<string>>(new Set(initial.map((row) => row.id)));

  const refresh = useCallback(() => {
    void fetchCases({ limit: 100 })
      .then(({ cases: next }) => {
        const arrived = next
          .filter((row) => !knownIds.current.has(row.id))
          .map((row) => row.id);
        next.forEach((row) => knownIds.current.add(row.id));
        setCases(next);

        if (arrived.length === 0) return;
        setFlashing((current) => new Set([...current, ...arrived]));
        setTimeout(() => {
          setFlashing((current) => {
            const remaining = new Set(current);
            arrived.forEach((id) => remaining.delete(id));
            return remaining;
          });
        }, FLASH_MS);
      })
      .catch(() => {
        /* Keep the rows already on screen; one failed poll is not an empty list. */
      });
  }, []);

  useRealtimeCases(refresh);

  const header = (
    <PageHeader
      title="Cases"
      subtitle={`${cases.length} recovery case${cases.length === 1 ? "" : "s"}`}
    />
  );

  if (cases.length === 0) {
    return (
      <>
        {header}
        {emptyState}
      </>
    );
  }

  return (
    <>
      {header}
      <div className="overflow-x-auto rounded-xl border border-hairline bg-elevated">
        <Table>
          <TableHeader>
            <TableRow className="border-hairline">
              <TableHead className="text-xs font-medium text-ink-faint">
                Status
              </TableHead>
              <TableHead className="text-xs font-medium text-ink-faint">
                Customer
              </TableHead>
              <TableHead className="text-xs font-medium text-ink-faint">
                Playbook
              </TableHead>
              <TableHead className="text-right text-xs font-medium text-ink-faint">
                At Risk
              </TableHead>
              <TableHead className="text-right text-xs font-medium text-ink-faint">
                Recovered
              </TableHead>
              <TableHead className="text-xs font-medium text-ink-faint">
                Opened
              </TableHead>
              <TableHead className="text-xs font-medium text-ink-faint">
                Step
              </TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {cases.map((row) => (
              <TableRow
                key={row.id}
                className={`border-hairline transition-colors duration-150 hover:bg-subtle ${
                  flashing.has(row.id) ? "animate-row-flash" : ""
                }`}
              >
                <TableCell>
                  <CaseStatusBadge status={row.status} />
                </TableCell>
                <TableCell className="text-sm font-medium text-ink">
                  {/* The link lives on the name and the arrow rather than on the
                    row: a `tr` cannot contain an anchor that covers it without
                    breaking the table semantics screen readers rely on. */}
                  <Link
                    href={`/app/cases/${row.id}`}
                    className="hover:underline"
                  >
                    {row.customers?.name ?? "—"}
                  </Link>
                </TableCell>
                <TableCell>
                  <PlaybookBadge playbook={row.playbook} />
                </TableCell>
                <TableCell className="text-right font-mono text-sm text-ink">
                  {formatINR(row.amount_at_risk_cents)}
                </TableCell>
                <TableCell
                  className={`text-right font-mono text-sm ${
                    row.amount_recovered_cents > 0
                      ? "text-success"
                      : "text-ink-faint"
                  }`}
                >
                  {row.amount_recovered_cents > 0
                    ? formatINR(row.amount_recovered_cents)
                    : "—"}
                </TableCell>
                <TableCell className="text-xs text-ink-faint">
                  {formatRelativeTime(row.opened_at)}
                </TableCell>
                <TableCell>
                  <span className="rounded bg-subtle px-2 py-0.5 font-mono text-xs text-ink-faint">
                    {row.current_step ?? "—"}
                  </span>
                </TableCell>
                <TableCell>
                  <Link
                    href={`/app/cases/${row.id}`}
                    aria-label={`Open case for ${row.customers?.name ?? "customer"}`}
                  >
                    <ArrowRight size={14} className="text-ink-faint" />
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}
