import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

import { env } from "@/lib/env";
import type { CookiesToSet, Database } from "@/lib/supabase/types";

/**
 * Supabase client for server components, server actions, and route handlers.
 *
 * `cookies()` is async in Next.js 16, so this function is too — every call site
 * must await it.
 *
 * Server *components* cannot write cookies. The `setAll` below therefore
 * swallows the resulting error: session refresh is handled in proxy.ts, which
 * runs before rendering and can write, so nothing is actually lost.
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient<Database>(env.supabaseUrl, env.supabaseAnonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet: CookiesToSet) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Called from a server component. proxy.ts already refreshed the
          // session, so ignoring this is safe.
        }
      },
    },
  });
}
