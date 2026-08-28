/**
 * Typed client for the batch simulator.
 *
 * The wire shape is mixed and the types below say so rather than smoothing it
 * over. The endpoint envelope goes through `CamelModel`, so `batchId` and
 * `nCases` are camelCase; `result` is a serialised Python dataclass and stays
 * snake_case. Normalising one into the other would mean a second copy of the
 * result schema to keep in agreement with `BatchResult`.
 *
 * **Money here is in rupees, not paise.** Every other money field in this app
 * is paise, because that is what the database stores. A batch result never
 * touches a money column — it is a simulation — so it is denominated in whole
 * rupees, and `formatRupees` exists for exactly these fields.
 */

import { request } from "@/lib/api/client";

export interface BatchWindow {
  cases: number;
  /** 0-1. */
  bandit_rate: number;
  baseline_rate: number;
}

export interface ComplianceSummary {
  /** Violations that escaped the guardrail. Structurally zero. */
  rbi_violations: number;
  trai_violations: number;
  /** Sends the guardrail stopped. Expected, and not a fault rate. */
  rbi_blocks: number;
  trai_blocks: number;
  opt_outs_honored: number;
  avg_opt_out_response_seconds: number;
  human_handoffs: number;
}

export interface BatchResult {
  total_cases: number;
  total_at_risk_inr: number;
  gross_recovered_inr: number;
  incremental_recovered_inr: number;
  recovery_rate_by_playbook: Record<string, number>;
  recovery_rate_by_policy: Record<string, number>;
  /** The same rates over the last quarter — the converged policy. */
  settled_recovery_rate_by_policy: Record<string, number>;
  settled_recovery_rate_by_playbook: Record<string, number>;
  compliance_violations: number;
  opt_outs_honored: number;
  human_handoffs: number;
  cost_per_100_inr_recovered: number;
  /** Case number where the bandit went ahead and stayed there. 0 if never. */
  bandit_convergence_case: number;
  time_series: BatchWindow[];
  compliance_summary: ComplianceSummary;
  elapsed_seconds: number;
}

/** What the run's row holds while it is still going. */
export interface BatchProgress {
  progress: { cases_done: number; total: number; pct: number };
  current_bandit_rate: number | null;
  current_baseline_rate: number | null;
  time_series: BatchWindow[];
}

export type BatchStatus = "running" | "completed" | "failed";

export interface BatchRun {
  batchId: string;
  status: BatchStatus;
  nCases: number;
  /**
   * Null before the first progress tick, a `BatchProgress` while running, and a
   * `BatchResult` once complete. The two are told apart by whether `progress`
   * is present — see `isComplete`.
   */
  result: BatchProgress | BatchResult | null;
  error: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

export interface BatchStarted {
  batchId: string;
  status: string;
  estimatedSeconds: number;
}

/**
 * Whether a run's `result` is the finished article.
 *
 * Checked on the payload rather than on `status`, because a Realtime update
 * carries the row's new `result` and the two can arrive a moment apart. Reading
 * the shape means the screen never renders a completed result under a progress
 * bar, or the reverse.
 */
export function isComplete(result: BatchRun["result"]): result is BatchResult {
  return result !== null && "total_cases" in result;
}

export function isProgress(result: BatchRun["result"]): result is BatchProgress {
  return result !== null && "progress" in result;
}

export function startBatch(nCases = 1000): Promise<BatchStarted> {
  return request<BatchStarted>("/api/simulator/batch/start", {
    method: "POST",
    body: JSON.stringify({ nCases }),
  });
}

export function fetchBatch(batchId: string): Promise<BatchRun> {
  return request<BatchRun>(`/api/simulator/batch/${batchId}`);
}
