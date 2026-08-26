/**
 * Typed client for the simulator control plane.
 *
 * These endpoints only exist in a development environment — the backend router
 * 404s outside one — so every call here is reachable only from `/app/dev/*`.
 *
 * The shapes mirror the backend's Pydantic models, which render camelCase on
 * the wire via `CamelModel`. They are written by hand rather than generated:
 * one router's worth of types is not enough to justify wiring up
 * openapi-typescript, and hand-written types can carry the comments that
 * explain what a field means.
 */

import { request } from "@/lib/api/client";

/** The playbooks a case can belong to. Mirrors `recovery_cases.playbook`. */
export type Playbook =
  | "failed_payment"
  | "checkout_abandonment"
  | "subscription_failure"
  | "b2b_overdue";

export type EventType =
  | "payment.failed"
  | "checkout.abandoned"
  | "subscription.charged.failed"
  | "invoice.overdue"
  | "customer.replied";

export type ReplyChannel = "whatsapp" | "sms" | "email";

export interface ScenarioMeta {
  code: string;
  personaName: string | null;
  personaExternalId: string | null;
  merchantContext: string;
  playbook: Playbook | null;
  amountAtRiskInr: number | null;
  amountAtRiskCents: number | null;
  eventType: EventType | null;
  oneLineDescription: string;
  videoExpectedPath: string;
  /** True for the batch beats (B1, B2), which write nothing until Phase 11. */
  deferred: boolean;
  /** Exactly what firing this scenario would write to `events.payload`. */
  samplePayload: Record<string, unknown> | null;
}

export interface ReplyExample {
  text: string;
  expectedIntent: string;
  language: string;
}

export interface FixtureCounts {
  customers: number;
  paymentMethods: number;
  events: number;
  cases: number;
}

export interface LoadedCounts {
  customers: number;
  customersCreated: number;
  paymentMethods: number;
  personas: string[];
}

export interface LoadFixturesResponse {
  loaded: LoadedCounts;
  message: string;
}

export interface ResetFixturesResponse {
  deleted: Record<string, number>;
  message: string;
}

export interface FixtureStatus {
  loaded: boolean;
  counts: FixtureCounts;
  personas: string[];
  scenarios: ScenarioMeta[];
  replyExamples: ReplyExample[];
}

export interface FireScenarioResponse {
  caseId: string | null;
  eventId: string | null;
  /** Set only by B3, which fires eight events at once. */
  caseIds?: string[] | null;
  eventIds?: string[] | null;
  scenarioCode: string;
  message: string;
}

export interface InjectReplyRequest {
  caseId: string;
  channel: ReplyChannel;
  rawText: string;
}

export interface InjectReplyResponse {
  replyId: string;
  message: string;
}

export interface RecentEvent {
  id: string;
  eventType: EventType;
  payload: Record<string, unknown>;
  receivedAt: string;
  customerName: string | null;
}

export interface InFlightCase {
  id: string;
  playbook: Playbook;
  status: string;
  amountAtRiskCents: number;
  openedAt: string;
  customerName: string | null;
}

export interface SimulatorStatus {
  fixturesLoaded: boolean;
  recentEvents: RecentEvent[];
  inFlightCases: InFlightCase[];
}

export function loadFixtures(): Promise<LoadFixturesResponse> {
  return request<LoadFixturesResponse>("/api/simulator/fixtures/load", { method: "POST" });
}

export function resetFixtures(): Promise<ResetFixturesResponse> {
  return request<ResetFixturesResponse>("/api/simulator/fixtures/reset", { method: "POST" });
}

export function getFixtureStatus(): Promise<FixtureStatus> {
  return request<FixtureStatus>("/api/simulator/fixtures/status");
}

export function fireScenario(code: string): Promise<FireScenarioResponse> {
  return request<FireScenarioResponse>(`/api/simulator/scenarios/${encodeURIComponent(code)}`, {
    method: "POST",
  });
}

export function injectReply(payload: InjectReplyRequest): Promise<InjectReplyResponse> {
  return request<InjectReplyResponse>("/api/simulator/replies", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getSimulatorStatus(): Promise<SimulatorStatus> {
  return request<SimulatorStatus>("/api/simulator/status");
}
