import "server-only";

/**
 * Server-only read for the uplift ROI panel.
 *
 * Split from `roi.ts` for the same reason as `cases.server.ts`: `serverRequest`
 * reaches the session through `next/headers`, and the seed button is a client
 * component that needs the types from the other half.
 */

import { serverRequest } from "@/lib/api/server";
import type { UpliftRoi } from "@/lib/api/roi";

export function getUpliftRoi(playbook?: string): Promise<UpliftRoi> {
  const query = playbook ? `?playbook=${encodeURIComponent(playbook)}` : "";
  return serverRequest<UpliftRoi>(`/api/analytics/uplift${query}`);
}
