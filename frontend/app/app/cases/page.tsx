import type { Metadata } from "next";
import Link from "next/link";

import { CasesRealtimeUpdater } from "@/components/domain/CasesRealtimeUpdater";
import { PageHeader } from "@/components/shell/PageHeader";
import type { CaseListItem } from "@/lib/api/cases";
import { getCases } from "@/lib/api/cases.server";

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

  if (failed) {
    return (
      <>
        <PageHeader title="Cases" subtitle="Could not reach the API" />
        <div className="rounded-xl border border-hairline bg-elevated p-12 text-center">
          <p className="text-sm text-ink-muted">Could not load cases.</p>
          <p className="mt-1 text-xs text-ink-faint">
            The API did not respond. Refresh once it is back.
          </p>
        </div>
      </>
    );
  }

  // The list is server-rendered for the first paint and then owned by the
  // island, which re-reads on every Realtime change. The header goes with it so
  // the case count in the subtitle cannot drift from the rows below it.
  return (
    <CasesRealtimeUpdater
      initial={cases}
      emptyState={
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
      }
    />
  );
}
