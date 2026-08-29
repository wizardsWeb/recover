"use client";

import { useCallback, useRef, useState, type ReactNode } from "react";

import { CasesTable } from "@/components/domain/CasesTable";
import { PageHeader } from "@/components/shell/PageHeader";
import { fetchCases, type CaseListItem } from "@/lib/api/cases";
import { useRealtimeCases } from "@/lib/hooks/useRealtimeCases";

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
      <CasesTable cases={cases} variant="full" flashingIds={flashing} />
    </>
  );
}
