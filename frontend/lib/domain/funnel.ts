import type { CaseListItem } from "@/lib/api/cases";
import { stepIndex } from "@/lib/domain/case-steps";

export interface FunnelStage {
  label: string;
  count: number;
}

/**
 * The four funnel stages, derived from the case rows the dashboard already has.
 *
 * There is no funnel endpoint and the backend is not being changed for this, so
 * the stages are computed from `current_step` and `status` — the two columns
 * that actually record how far a case got. Each stage is *cumulative*: a
 * recovered case is counted in all four, because a funnel whose stages are
 * disjoint is a bar chart wearing a funnel's shape.
 *
 * The rules, and what each one is really asking:
 *
 *   * **Opened** — every case in the window. The denominator.
 *   * **Diagnosed** — reached `diagnose`. A case sitting at `detect` has been
 *     noticed and not yet understood.
 *   * **Acted** — reached `execute`. This is the stage that matters most and
 *     the one most easily overstated: a case blocked at the guardrail did *not*
 *     act, and counting it here would quietly turn every compliance stop into a
 *     success.
 *   * **Recovered** — the money came back. Status, not step, because a case can
 *     sit at `listen` for days and still be recovered at the end of it.
 *
 * A closed case may have a null `current_step`, so terminal statuses are read
 * as having passed the stages they must have passed to reach that status.
 */
export function funnelFrom(cases: readonly CaseListItem[]): FunnelStage[] {
  const terminal = new Set(["recovered", "failed", "stopped"]);
  let diagnosed = 0;
  let acted = 0;
  let recovered = 0;

  for (const row of cases) {
    const index = stepIndex(row.current_step);
    const closed = terminal.has(row.status);

    // A case that is closed got at least as far as diagnosis; nothing closes a
    // case before it has been looked at.
    if (index >= stepIndex("diagnose") || closed) diagnosed += 1;
    // `stopped` is the exception among the terminal statuses: it means the
    // agent stood down, which is precisely the case that did not act.
    if (index >= stepIndex("execute") || row.status === "recovered" || row.status === "failed") {
      acted += 1;
    }
    if (row.status === "recovered") recovered += 1;
  }

  return [
    { label: "Opened", count: cases.length },
    { label: "Diagnosed", count: diagnosed },
    { label: "Acted", count: acted },
    { label: "Recovered", count: recovered },
  ];
}
