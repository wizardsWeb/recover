import "server-only";

/**
 * Server-only read for the batch page's initial state.
 *
 * A 404 means no run has ever happened, which is the empty state rather than an
 * error — so it is translated to null here and the page branches on that.
 */

import { ApiError } from "@/lib/api/client";
import { serverRequest } from "@/lib/api/server";
import type { BatchRun } from "@/lib/api/batch";

export async function getLatestBatch(): Promise<BatchRun | null> {
  try {
    return await serverRequest<BatchRun>("/api/simulator/batch/latest");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
