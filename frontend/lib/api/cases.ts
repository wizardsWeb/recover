/**
 * Typed client for the cases, audit and analytics endpoints.
 *
 * These routers return **snake_case**, unlike the merchant and simulator ones,
 * which render camelCase through `CamelModel`. The reason is that a case
 * response is a deep tree — the row plus its audit events, decisions, execution
 * attempts and replies — and re-modelling all of it in Pydantic just to change
 * the casing would mean maintaining a second copy of the schema. The types
 * below mirror the database columns exactly, which is also what makes them easy
 * to check against the migration.
 *
 * This module is **browser-safe**: it holds the types and the one action a user
 * takes (`overrideCase`). The read functions live in `cases.server.ts`, because
 * they reach for the session through `next/headers` and importing that from a
 * client component fails the build. Splitting on that boundary is what keeps
 * `CaseActions` — a client component that needs these types — importable.
 */

import { request } from "@/lib/api/client";

export type CaseStatus =
  | "open"
  | "in_flight"
  | "recovered"
  | "stopped"
  | "failed"
  | "holdout";

export type Playbook =
  | "failed_payment"
  | "checkout_abandonment"
  | "subscription_failure"
  | "b2b_overdue";

export interface CaseListItem {
  id: string;
  status: CaseStatus;
  playbook: Playbook;
  amount_at_risk_cents: number;
  amount_recovered_cents: number;
  opened_at: string;
  closed_at: string | null;
  current_step: string | null;
  uplift_bucket: string | null;
  customers: { name: string | null; email: string | null } | null;
}

export interface AuditEvent {
  id: string;
  case_id: string | null;
  actor: "agent" | "human" | "system" | "customer";
  /** `<step>:<label>`, e.g. `guardrail:guardrail_block`. */
  event: string;
  details: Record<string, unknown>;
  trace_id: string | null;
  created_at: string;
}

export interface BanditAlternative {
  arm_name: string;
  expected_reward: number;
  chosen: boolean;
  not_chosen_reason: string | null;
}

export interface AgentDecision {
  id: string;
  step_name: string;
  step_number: number;
  decision_source: string | null;
  bandit_chosen_arm: string | null;
  bandit_arm_confidence: number | null;
  bandit_mode: "exploit" | "explore" | null;
  bandit_alternatives: BanditAlternative[] | null;
  chosen_action: string | null;
  action_params: Record<string, unknown> | null;
  reasoning: string | null;
  created_at: string;
}

export interface ExecutionAttempt {
  id: string;
  action_type: string;
  adapter: string;
  status: "pending" | "success" | "failure" | "simulated" | "cancelled";
  request_payload: Record<string, unknown> | null;
  response_payload: Record<string, unknown> | null;
  idempotency_key: string | null;
  attempted_at: string;
}

export interface CustomerReply {
  id: string;
  channel: string;
  raw_text: string;
  llm_classification: Record<string, unknown> | null;
  applied_state_update: string | null;
  received_at: string;
}

export interface CaseCustomer {
  id: string;
  name: string | null;
  email: string | null;
  phone: string | null;
  ltv_cents: number;
  tenure_days: number;
  consent: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

export interface CaseDetail extends Omit<CaseListItem, "customers"> {
  diagnosis: Record<string, unknown> | null;
  customers: CaseCustomer | null;
  audit_events: AuditEvent[];
  agent_decisions: AgentDecision[];
  execution_attempts: ExecutionAttempt[];
  customer_replies: CustomerReply[];
}

export interface Overview {
  cases_opened_today: number;
  cases_in_flight: number;
  amount_at_risk_today_cents: number;
  amount_recovered_today_cents: number;
  recovery_rate_today: number;
  compliance_violations_today: number;
}

export interface CaseFilters {
  status?: string;
  playbook?: string;
  limit?: number;
  offset?: number;
}

/** Take a case away from the agent. Runs in the browser — it is a user action. */
export function overrideCase(
  id: string,
  action: "pause" | "stop" | "escalate",
  reason?: string,
): Promise<{ case_id: string; action: string; new_status: string }> {
  return request(`/api/cases/${id}/override`, {
    method: "POST",
    body: JSON.stringify({ action, reason }),
  });
}
