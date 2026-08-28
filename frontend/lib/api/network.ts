/**
 * Typed client for the network intelligence endpoints.
 *
 * Snake_case on the wire, like the rest of the analytics-shaped routers. The
 * simulator's downtime endpoint is the exception — it goes through `CamelModel`
 * — and the types below mirror each one as it actually arrives rather than
 * normalising, so a field can be checked against the endpoint that produces it.
 *
 * Browser-safe. The three reads live in `network.server.ts`; what stays here is
 * the WebSocket, which is inherently a client concern, and the two dev actions.
 */

import { request } from "@/lib/api/client";
import { createClient } from "@/lib/supabase/client";
import { env } from "@/lib/env";

export type AlertSeverity = "low" | "medium" | "high" | "critical";

export interface NetworkAlert {
  id: string;
  alert_type: string;
  bank: string | null;
  method: string | null;
  severity: AlertSeverity;
  z_score: number | null;
  sample_size: number | null;
  affected_merchants_count: number | null;
  network_wide_success_rate: number | null;
  baseline_rate: number | null;
  detected_at: string;
  resolved_at: string | null;
}

export interface AlertsResponse {
  active: NetworkAlert[];
  recent: NetworkAlert[];
  total_active: number;
  checked_at: string;
}

export interface HeatmapCell {
  bank: string;
  method: string;
  /** 0-23, IST. */
  hour: number;
  /** 0-1. */
  success_rate: number;
  sample_size: number;
}

export interface HeatmapResponse {
  banks: string[];
  hours: number[];
  methods: string[];
  cells: HeatmapCell[];
  /** Most cells are below the sample floor — the grid is indicative, not measured. */
  is_sparse: boolean;
  note: string | null;
}

export interface BenchmarkResponse {
  merchant_rate: number | null;
  vertical_median: number | null;
  vertical_top_decile: number | null;
  percentile: number | null;
  sample_size: number;
  peer_merchants: number;
  /**
   * Which comparison the numbers represent. `network_too_small` means the peer
   * group could be identified from a median, so none was computed — the UI says
   * that rather than rendering a blank.
   */
  basis: "network" | "network_too_small" | "no_closed_cases";
}

/** The raw shape of a message on the alerts channel. */
export type StreamEvent =
  | { type: "connected"; channel: string }
  | { type: "heartbeat"; at: string }
  | { type: "alert_fired"; alert: Record<string, unknown> }
  | { type: "alert_resolved"; alert: Record<string, unknown> };

export interface DowntimeRequest {
  bank: string;
  method: string;
  severity: "medium" | "high" | "critical";
  durationMinutes: number;
}

export interface DowntimeResponse {
  alertId: string;
  bank: string;
  method: string;
  severity: string;
  successRate: number;
  willResolveAt: string;
}

/**
 * Re-read the heatmap from the browser.
 *
 * The method tabs change one query parameter, and routing that through a server
 * round trip would re-render the alert banner and drop its WebSocket. Fetching
 * here keeps the switch local to the grid.
 */
export function fetchHeatmap(method?: string): Promise<HeatmapResponse> {
  const query = method ? `?method=${encodeURIComponent(method)}` : "";
  return request<HeatmapResponse>(`/api/network/heatmap${query}`);
}

/** Re-read the alerts. Used to reconcile after the socket reports a change. */
export function fetchAlerts(): Promise<AlertsResponse> {
  return request<AlertsResponse>("/api/network/alerts");
}

export interface NetworkSeedResponse {
  rows: number;
  cleared: number;
  days: number;
  instruments: number;
  banks: string[];
  methods: string[];
}

/** Dev-only: fill the heatmap with a week of plausible payment behaviour. */
export function seedNetworkStats(days = 7): Promise<NetworkSeedResponse> {
  return request<NetworkSeedResponse>("/api/simulator/network/seed", {
    method: "POST",
    body: JSON.stringify({ days }),
  });
}

/** Dev-only: take a bank down for a fixed window. */
export function triggerDowntime(payload: DowntimeRequest): Promise<DowntimeResponse> {
  return request<DowntimeResponse>("/api/simulator/network/downtime", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Build the authenticated WebSocket URL for the alerts stream.
 *
 * The token goes in the query string because a browser cannot set an
 * `Authorization` header on a WebSocket handshake — that is a limitation of the
 * API, not a shortcut. Returns null when there is no session, so the caller can
 * skip connecting rather than opening a socket the server will immediately
 * close.
 */
export async function alertStreamUrl(): Promise<string | null> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) return null;

  const base = env.apiBaseUrl.replace(/^http/, "ws");
  return `${base}/api/network/alerts/stream?token=${encodeURIComponent(session.access_token)}`;
}
