/**
 * Server-side counterpart to `request` in `client.ts`.
 *
 * The difference is where the session comes from. `client.ts` reads it from the
 * browser's Supabase client; a Server Component has no browser, so the token
 * has to come from the cookie store via `@/lib/supabase/server`. Everything
 * else — the bearer header, the error envelope, the trace id — is identical,
 * because it is the same API on the other end.
 *
 * Why fetch through the API at all instead of querying Supabase directly from
 * the server? Because the domain logic lives in FastAPI. A page that read
 * `recovery_cases` itself would be a second implementation of what a case is,
 * and the two would drift the first time a column changed meaning.
 */

import { ApiError } from "@/lib/api/client";
import { env } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

interface ErrorEnvelope {
  error?: { message?: string };
}

export async function serverRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const supabase = await createClient();
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
    // Case state changes while the agent works. A cached page would show a
    // recovery that finished minutes ago as still in flight.
    cache: "no-store",
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

  return (await response.json()) as T;
}
