import "server-only";

/**
 * Server-only reads for cases, audit and analytics.
 *
 * Separate from `cases.ts` because `serverRequest` reaches the session through
 * `next/headers`, which cannot be bundled for the browser. A client component
 * importing a module that transitively pulls it in fails the build — so the
 * `server-only` marker above turns that into an immediate, readable error
 * rather than a bundler trace through four files.
 */

import { serverRequest } from "@/lib/api/server";
import type { AuditEvent, CaseDetail, CaseFilters, CaseListItem, Overview } from "@/lib/api/cases";

export function getCases(filters: CaseFilters = {}): Promise<{ cases: CaseListItem[] }> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.playbook) params.set("playbook", filters.playbook);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));
  const query = params.toString();
  return serverRequest<{ cases: CaseListItem[] }>(`/api/cases${query ? `?${query}` : ""}`);
}

export function getCase(id: string): Promise<CaseDetail> {
  return serverRequest<CaseDetail>(`/api/cases/${id}`);
}

export function getAuditEvents(limit = 100): Promise<{ audit_events: AuditEvent[] }> {
  return serverRequest<{ audit_events: AuditEvent[] }>(`/api/audit?limit=${limit}`);
}

export function getOverview(): Promise<Overview> {
  return serverRequest<Overview>("/api/analytics/overview");
}
