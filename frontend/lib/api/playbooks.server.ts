import "server-only";

/**
 * Server-only playbook reads. See `cases.server.ts` for why the split exists.
 */

import { serverRequest } from "@/lib/api/server";
import type {
  BanditArmPosterior,
  PlaybookDetail,
  PlaybookSummary,
} from "@/lib/api/playbooks";

export function getPlaybooks(): Promise<{ playbooks: PlaybookSummary[] }> {
  return serverRequest<{ playbooks: PlaybookSummary[] }>("/api/playbooks");
}

export function getPlaybook(slug: string): Promise<PlaybookDetail> {
  return serverRequest<PlaybookDetail>(`/api/playbooks/${slug}`);
}

export function getBanditPosteriors(
  playbook: string,
  contextBucket?: string,
): Promise<{ playbook: string; context_bucket: string | null; arms: BanditArmPosterior[] }> {
  const query = contextBucket ? `&context_bucket=${encodeURIComponent(contextBucket)}` : "";
  return serverRequest(`/api/analytics/bandit-posteriors?playbook=${playbook}${query}`);
}
