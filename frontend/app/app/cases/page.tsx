import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

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
import type { CaseListItem } from "@/lib/api/cases";
import { getCases } from "@/lib/api/cases.server";
import { formatINR, formatRelativeTime } from "@/lib/utils/format";

export const metadata: Metadata = { title: "Cases" };

export default async function CasesPage() {
  let cases: CaseListItem[] = [];
  let failed = false;
  try {
    cases = (await getCases({ limit: 100 })).cases;
  } catch {
    // The backend being unreachable is not the same as having no cases, and
    // showing "no cases yet" for a connection failure would quietly tell a
    // merchant their recoveries had vanished.
    failed = true;
  }

  return (
    <>
      <PageHeader
        title="Cases"
        subtitle={
          failed
            ? "Could not reach the API"
            : `${cases.length} recovery case${cases.length === 1 ? "" : "s"}`
        }
      />

      {failed ? (
        <div className="rounded-xl border border-hairline bg-elevated p-12 text-center">
          <p className="text-sm text-ink-muted">Could not load cases.</p>
          <p className="mt-1 text-xs text-ink-faint">
            The API did not respond. Refresh once it is back.
          </p>
        </div>
      ) : cases.length === 0 ? (
        <div className="rounded-xl border border-hairline bg-elevated p-12 text-center">
          <p className="text-sm text-ink-faint">No cases yet.</p>
          <p className="mt-1 text-xs text-ink-faint">
            Fire a scenario from the{" "}
            <Link href="/app/dev/simulator" className="underline">
              Simulator
            </Link>{" "}
            to see cases appear here.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-hairline bg-elevated">
          <Table>
            <TableHeader>
              <TableRow className="border-hairline">
                <TableHead className="text-xs font-medium text-ink-faint">Status</TableHead>
                <TableHead className="text-xs font-medium text-ink-faint">Customer</TableHead>
                <TableHead className="text-xs font-medium text-ink-faint">Playbook</TableHead>
                <TableHead className="text-right text-xs font-medium text-ink-faint">
                  At Risk
                </TableHead>
                <TableHead className="text-right text-xs font-medium text-ink-faint">
                  Recovered
                </TableHead>
                <TableHead className="text-xs font-medium text-ink-faint">Opened</TableHead>
                <TableHead className="text-xs font-medium text-ink-faint">Step</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {cases.map((row) => (
                <TableRow key={row.id} className="border-hairline transition-colors hover:bg-subtle">
                  <TableCell>
                    <CaseStatusBadge status={row.status} />
                  </TableCell>
                  <TableCell className="text-sm font-medium text-ink">
                    {/* The link lives on the name and the arrow rather than on the
                        row: a `tr` cannot contain an anchor that covers it without
                        breaking the table semantics screen readers rely on. */}
                    <Link href={`/app/cases/${row.id}`} className="hover:underline">
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
                      row.amount_recovered_cents > 0 ? "text-success" : "text-ink-faint"
                    }`}
                  >
                    {row.amount_recovered_cents > 0 ? formatINR(row.amount_recovered_cents) : "—"}
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
      )}
    </>
  );
}
