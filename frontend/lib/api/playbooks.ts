/**
 * Playbook types and the one mutation a merchant can make from the UI.
 *
 * Browser-safe, like `cases.ts`: the reads live in `playbooks.server.ts` because
 * they reach for the session through `next/headers`. The toggle stays here so a
 * client component can call it without dragging server-only code into the
 * browser bundle.
 */

import { request } from "@/lib/api/client";
import type { CaseListItem, Playbook } from "@/lib/api/cases";

export interface PlaybookStats {
  totalCases: number;
  casesOpen: number;
  casesInFlight: number;
  casesRecovered: number;
  recoveryRate: number;
  amountAtRiskCents: number;
  amountRecoveredCents: number;
  /** Null until something has been recovered — a zero would read as "instant". */
  avgHoursToRecovery: number | null;
}

export interface PlaybookSummary {
  slug: Playbook;
  label: string;
  description: string;
  enabled: boolean;
  defaultArm: string;
  armCount: number;
  stats: PlaybookStats;
}

/** The compliance envelope: what the agent is allowed to do, not what it did. */
export interface PlaybookConfig {
  arms: string[];
  default_arm: string;
  max_total_attempts: number;
  max_messages_per_day: number;
  max_messages_per_week: number;
  max_discount_pct: number;
  rbi_max_retries_per_cycle: number;
  rbi_min_hours_between_retries: number;
  hard_stop_after_days: number;
  channels_allowed: string[];
  human_escalation_after_attempts: number;
}

export interface PlaybookDetail {
  slug: Playbook;
  label: string;
  description: string;
  enabled: boolean;
  stats: PlaybookStats;
  config: PlaybookConfig;
  recent_cases: CaseListItem[];
}

export interface BanditArmPosterior {
  arm_name: string;
  context_bucket: string | null;
  alpha: number;
  beta: number;
  n_pulls: number;
  expected_win_rate: number;
  ci_low: number;
  ci_high: number;
  last_updated_at: string | null;
}

export function togglePlaybook(slug: string): Promise<{ slug: string; enabled: boolean }> {
  return request(`/api/playbooks/${slug}/toggle`, { method: "PATCH" });
}
