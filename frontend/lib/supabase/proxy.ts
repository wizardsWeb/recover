import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import { env } from "@/lib/env";
import type { CookiesToSet, Database } from "@/lib/supabase/types";

/** Routes that require a session. */
const PROTECTED_PREFIXES = ["/app", "/onboarding"] as const;

/** Routes a signed-in user has no reason to see. */
const AUTH_ROUTES = ["/login", "/signup"] as const;

/**
 * Refresh the Supabase session and enforce the route guards.
 *
 * This runs before every matched request, which is what makes it the right
 * place to write refreshed auth cookies — server components cannot.
 *
 * The response object is threaded through carefully: `supabase.auth.getUser()`
 * may rotate the tokens, and those `Set-Cookie` headers have to survive onto
 * whatever response we ultimately return.
 */
export async function updateSession(request: NextRequest): Promise<NextResponse> {
  let response = NextResponse.next({ request });

  const supabase = createServerClient<Database>(env.supabaseUrl, env.supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet: CookiesToSet) {
        for (const { name, value } of cookiesToSet) {
          request.cookies.set(name, value);
        }
        response = NextResponse.next({ request });
        for (const { name, value, options } of cookiesToSet) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  // getUser() revalidates against the Supabase auth server. getSession() only
  // decodes the cookie, which a client could have tampered with, so it must not
  // be used for an authorisation decision.
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { pathname } = request.nextUrl;
  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
  const isAuthRoute = AUTH_ROUTES.some((route) => pathname === route);

  if (isProtected && !user) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/login";
    // Remember where they were headed so login can send them back.
    redirectUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(redirectUrl);
  }

  if (isAuthRoute && user) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/app";
    redirectUrl.search = "";
    return NextResponse.redirect(redirectUrl);
  }

  return response;
}
