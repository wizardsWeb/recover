"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { EventLogTail } from "./EventLogTail";
import { FixturePanel } from "./FixturePanel";
import { ReplyInjector } from "./ReplyInjector";
import { ScenarioRunner } from "./ScenarioRunner";

interface RefreshContextValue {
  /** Increments whenever one panel does something the others should notice. */
  token: number;
  refresh: () => void;
}

const RefreshContext = createContext<RefreshContextValue>({ token: 0, refresh: () => {} });

/**
 * Lets the panels stay independent while still reacting to each other.
 *
 * Firing a scenario has to update the fixture counts, the case dropdown, and
 * the event tail — three sibling components with no data in common. Lifting all
 * of their state into one parent would couple four panels to one fetch; a
 * counter they each watch keeps them separate and costs one integer.
 */
export function useSimulatorRefresh(): RefreshContextValue {
  return useContext(RefreshContext);
}

export function SimulatorPanels() {
  const [token, setToken] = useState(0);
  const refresh = useCallback(() => setToken((previous) => previous + 1), []);
  const value = useMemo(() => ({ token, refresh }), [token, refresh]);

  return (
    <RefreshContext.Provider value={value}>
      <div className="grid gap-4 lg:grid-cols-2">
        <FixturePanel />
        <EventLogTail />
      </div>
      <div className="mt-4 space-y-4">
        <ScenarioRunner />
        <ReplyInjector />
      </div>
    </RefreshContext.Provider>
  );
}

/** Shared chrome so the four panels read as one instrument. */
export function Panel({
  id,
  title,
  description,
  actions,
  children,
  className,
}: {
  id?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      id={id}
      className={`flex flex-col rounded-lg border border-hairline bg-elevated ${className ?? ""}`}
    >
      <header className="flex items-start justify-between gap-3 border-b border-hairline px-4 py-3">
        <div>
          <h2 className="font-display text-sm font-semibold tracking-[-0.01em] text-ink">
            {title}
          </h2>
          {description ? <p className="mt-0.5 text-xs text-ink-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </header>
      <div className="flex-1 p-4">{children}</div>
    </section>
  );
}
