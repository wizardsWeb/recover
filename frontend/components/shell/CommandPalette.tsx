"use client";

import { useRouter } from "next/navigation";
import { FlaskConical, PlayCircle, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { NAV_ITEMS } from "@/components/shell/nav";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { fetchCases, type CaseListItem } from "@/lib/api/cases";
import { loadFixtures } from "@/lib/api/simulator";
import { isLocal } from "@/lib/env";
import { formatINR } from "@/lib/utils/format";

const RECENT_CASE_LIMIT = 5;

/**
 * The header search box and the ⌘K palette it opens.
 *
 * Trigger and dialog live in one component so the shell does not have to thread
 * an `open` callback down through server components — `AppShell` and `Header`
 * are server-rendered, and a context provider spanning them would force both
 * into the client bundle to serve one button.
 *
 * Pages come from `NAV_ITEMS`, the same list the sidebar and breadcrumbs read.
 * A second hand-written list here is the kind that silently goes stale the
 * first time a section is added and only the sidebar is updated.
 *
 * Cases are fetched when the palette opens, not on mount: this component is in
 * the layout, so fetching eagerly would mean a request on every page load for a
 * list most visits never see.
 */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [cases, setCases] = useState<CaseListItem[]>([]);
  const [loadingFixtures, setLoadingFixtures] = useState(false);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== "k") return;
      if (!event.metaKey && !event.ctrlKey) return;
      // Otherwise the browser's own find-in-page / search shortcut also fires.
      event.preventDefault();
      setOpen((current) => !current);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void fetchCases({ limit: RECENT_CASE_LIMIT })
      .then(({ cases: next }) => {
        if (!cancelled) setCases(next);
      })
      .catch(() => {
        // A palette that still navigates is more useful than one that reports
        // it could not list cases, so the section simply stays empty.
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  const run = useCallback((action: () => void) => {
    setOpen(false);
    action();
  }, []);

  const onLoadFixtures = useCallback(() => {
    setOpen(false);
    setLoadingFixtures(true);
    void loadFixtures()
      .then(() => toast.success("Fixtures loaded"))
      .catch((error: unknown) =>
        toast.error(error instanceof Error ? error.message : "Could not load fixtures"),
      )
      .finally(() => setLoadingFixtures(false));
  }, []);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-center gap-2 rounded-md border border-hairline bg-subtle px-3 py-1.5 text-sm text-ink-faint transition-colors hover:border-edge hover:text-ink-muted"
      >
        <Search className="size-4 shrink-0" aria-hidden />
        <span className="flex-1 text-left">Search cases, customers, IDs…</span>
        <kbd className="rounded-sm border border-hairline bg-elevated px-1.5 py-0.5 font-mono text-[10px] text-ink-faint">
          ⌘K
        </kbd>
      </button>

      <CommandDialog
        open={open}
        onOpenChange={setOpen}
        title="Command palette"
        description="Jump to a case or a section, or run an action."
      >
        <CommandInput placeholder="Search cases and pages…" />
        <CommandList>
          <CommandEmpty>No matches.</CommandEmpty>

          {cases.length > 0 ? (
            <CommandGroup heading="Recent cases">
              {cases.map((row) => (
                <CommandItem
                  key={row.id}
                  // The searchable text. Without it cmdk would match on the
                  // rendered children only, and the id would not be findable.
                  value={`${row.customers?.name ?? "unknown"} ${row.status} ${row.id}`}
                  onSelect={() => run(() => router.push(`/app/cases/${row.id}`))}
                >
                  <span className="flex-1 truncate">{row.customers?.name ?? "Unknown"}</span>
                  <span className="ml-2 shrink-0 rounded-4xl bg-subtle px-2 py-0.5 text-[10px] text-ink-muted">
                    {row.status.replace(/_/g, " ")}
                  </span>
                  <span className="ml-2 shrink-0 font-mono text-xs text-ink-faint">
                    {formatINR(row.amount_at_risk_cents)}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}

          <CommandSeparator />

          <CommandGroup heading="Pages">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <CommandItem
                  key={item.href}
                  value={`${item.label} ${item.href}`}
                  onSelect={() => run(() => router.push(item.href))}
                >
                  <Icon className="size-4 shrink-0" aria-hidden />
                  <span>{item.label}</span>
                </CommandItem>
              );
            })}
            {isLocal ? (
              <CommandItem
                value="Simulator dev scenarios"
                onSelect={() => run(() => router.push("/app/dev/simulator"))}
              >
                <FlaskConical className="size-4 shrink-0" aria-hidden />
                <span>Simulator</span>
              </CommandItem>
            ) : null}
          </CommandGroup>

          {isLocal ? (
            <>
              <CommandSeparator />
              <CommandGroup heading="Actions">
                <CommandItem
                  value="Fire scenario simulator"
                  onSelect={() => run(() => router.push("/app/dev/simulator"))}
                >
                  <PlayCircle className="size-4 shrink-0" aria-hidden />
                  <span>Fire scenario…</span>
                </CommandItem>
                <CommandItem
                  value="Load fixtures personas priors"
                  disabled={loadingFixtures}
                  onSelect={onLoadFixtures}
                >
                  <FlaskConical className="size-4 shrink-0" aria-hidden />
                  <span>{loadingFixtures ? "Loading fixtures…" : "Load fixtures"}</span>
                </CommandItem>
              </CommandGroup>
            </>
          ) : null}
        </CommandList>
      </CommandDialog>
    </>
  );
}
