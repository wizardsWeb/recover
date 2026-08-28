import "server-only";

/**
 * Server-only reads for the network intelligence page.
 *
 * Split from `network.ts` for the reason `cases.server.ts` is: `serverRequest`
 * reaches the session through `next/headers`, and the alert banner is a client
 * component that needs the types from the other half.
 */

import { serverRequest } from "@/lib/api/server";
import type { AlertsResponse, BenchmarkResponse, HeatmapResponse } from "@/lib/api/network";

export function getHeatmap(method?: string): Promise<HeatmapResponse> {
  const query = method ? `?method=${encodeURIComponent(method)}` : "";
  return serverRequest<HeatmapResponse>(`/api/network/heatmap${query}`);
}

export function getAlerts(): Promise<AlertsResponse> {
  return serverRequest<AlertsResponse>("/api/network/alerts");
}

export function getBenchmark(): Promise<BenchmarkResponse> {
  return serverRequest<BenchmarkResponse>("/api/network/benchmark");
}
