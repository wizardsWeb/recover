/**
 * The agent loop's step vocabulary, in the order the loop runs them.
 *
 * Lives here rather than in `CaseTimeline` so that anything needing to reason
 * about *how far a case got* — the timeline, the dashboard funnel — reads one
 * list. Two copies is how a funnel starts counting `uplift_check` as an action
 * because somebody inserted a step in one file.
 */
export const STEP_ORDER = [
  "detect",
  "diagnose",
  "uplift_check",
  "decide",
  "guardrail",
  "execute",
  "listen",
  "learn",
  "audit",
] as const;

export type StepName = (typeof STEP_ORDER)[number];

/** Position in the loop, or `-1` for a step this build does not know about. */
export function stepIndex(step: string | null): number {
  if (!step) return -1;
  return STEP_ORDER.indexOf(step as StepName);
}
