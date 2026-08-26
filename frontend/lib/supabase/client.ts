"use client";

import { createBrowserClient } from "@supabase/ssr";

import { env } from "@/lib/env";
import type { Database } from "@/lib/supabase/types";

/**
 * Supabase client for use inside client components.
 *
 * `createBrowserClient` memoises internally, so calling this on every render is
 * cheap and there is no need for a module-level singleton.
 */
export function createClient() {
  return createBrowserClient<Database>(env.supabaseUrl, env.supabaseAnonKey);
}
