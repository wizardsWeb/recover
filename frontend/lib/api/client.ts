/**
 * Typed client for the FastAPI backend.
 *
 * Business logic lives in FastAPI, never in a Next.js route handler, so this is
 * the only path from the browser to the domain. Every call carries the caller's
 * Supabase access token, which the backend verifies and then uses to scope its
 * own Supabase queries — the same JWT enforces RLS on both sides.
 */

import { createClient } from "@/lib/supabase/client";
import { env } from "@/lib/env";
import type { Vertical } from "@/lib/supabase/types";

export interface Merchant {
  id: string;
  name: string;
  vertical: Vertical | null;
  onboarded: boolean;
  playbookConfig: Record<string, unknown>;
  timezone: string;
  createdAt: string;
  updatedAt: string;
}

export interface MerchantUpdate {
  name?: string;
  vertical?: Vertical;
  timezone?: string;
}

export interface MerchantOnboard {
  name: string;
  vertical: Vertical;
}

/** An error carrying the backend's status code, so callers can branch on it. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly traceId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ErrorEnvelope {
  error?: { message?: string };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    throw new ApiError(401, "Not signed in");
  }

  const response = await fetch(`${env.apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.access_token}`,
      ...init.headers,
    },
  });

  const traceId = response.headers.get("X-Trace-Id") ?? undefined;

  if (!response.ok) {
    let message = `Request failed with ${response.status}`;
    try {
      const body = (await response.json()) as ErrorEnvelope;
      if (body.error?.message) message = body.error.message;
    } catch {
      // Non-JSON error body; the status-based message above is what we have.
    }
    throw new ApiError(response.status, message, traceId);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function getMerchant(): Promise<Merchant> {
  return request<Merchant>("/api/merchants/me");
}

export function updateMerchant(payload: MerchantUpdate): Promise<Merchant> {
  return request<Merchant>("/api/merchants/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function onboardMerchant(payload: MerchantOnboard): Promise<Merchant> {
  return request<Merchant>("/api/merchants/onboard", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
