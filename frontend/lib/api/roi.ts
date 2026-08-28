/**
 * Typed client for the uplift ROI endpoint and the dev-only seeder.
 *
 * `/api/analytics/uplift` returns **snake_case**, like the rest of the
 * analytics router; `/api/simulator/uplift/seed` returns camelCase, because the
 * simulator router models its responses through `CamelModel`. The types below
 * mirror each one as it actually arrives rather than normalising, so a field
 * can be checked against the endpoint that produces it.
 *
 * Browser-safe: the read lives in `roi.server.ts`, which reaches for the
 * session through `next/headers`.
 */

import { request } from "@/lib/api/client";

export type UpliftBucket = "persuadable" | "sure_thing" | "lost_cause" | "dnd" | "unknown";

export interface UpliftBucketRow {
  bucket: UpliftBucket;
  treated_cases: number;
  /** 0-1. */
  treated_recovery_rate: number;
  control_cases: number;
  control_recovery_rate: number;
  /**
   * True when this bucket had too few controls of its own and the global
   * holdout rate stood in. The UI says so rather than presenting a borrowed
   * comparison as a measured one.
   */
  uses_global_control_rate: boolean;
  /** Treated rate minus control rate. Negative where contact hurt. */
  estimated_lift: number;
  gross_recovery_cents: number;
  /** Negative for a bucket the agent made worse. Not clamped. */
  incremental_recovery_cents: number;
}

export interface HoldoutStats {
  holdout_cases: number;
  resolved_controls: number;
  control_recoveries: number;
  control_recovery_rate: number;
  treated_cases: number;
  treated_recovery_rate: number;
  holdout_share: number;
  /** What the control group cost — absent until there are controls to price. */
  foregone_recovery_cents?: number;
}

export interface UpliftRoi {
  gross_recovery_cents: number;
  /** Null when no control group has resolved. Never a stand-in zero. */
  incremental_recovery_cents: number | null;
  incremental_pct_of_gross: number | null;
  is_estimable: boolean;
  bucket_breakdown: UpliftBucketRow[];
  holdout_stats: HoldoutStats;
  methodology_note: string;
}

export interface SeedUpliftResponse {
  cases: number;
  treated: number;
  controls: number;
  customers: number;
  models: Array<{
    playbook: string;
    status: string;
    treatedSamples: number;
    controlSamples: number;
    meanCate: number | null;
  }>;
}

/**
 * Manufacture a treated/control history and fit a model on it.
 *
 * Dev-only on both ends: the button is hidden outside a local environment and
 * the backend router 404s outside one.
 */
export function seedUpliftHistory(totalCases = 320): Promise<SeedUpliftResponse> {
  return request<SeedUpliftResponse>("/api/simulator/uplift/seed", {
    method: "POST",
    body: JSON.stringify({ totalCases }),
  });
}
