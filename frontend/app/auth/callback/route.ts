import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

/**
 * Where a confirmation or recovery email lands.
 *
 * Supabase's browser client uses PKCE, so the link in the email does not carry
 * a session — it carries a one-time `code` that has to be exchanged for one,
 * server-side, against the verifier cookie the browser stored at sign-up. Until
 * this route existed the code arrived on the marketing page, nothing consumed
 * it, and the proxy bounced the user to `/login` still signed out: confirmed,
 * and unable to tell why.
 *
 * Older email templates send `token_hash` and `type` instead of `code`. Both are
 * handled, because which one a project sends depends on whether its templates
 * have been customised — and a route that only understood one would work in
 * development and fail on whichever the deployed project happens to use.
 *
 * The exchange writes the session cookies through the same server client the
 * rest of the app reads, so by the time the redirect below is followed the
 * proxy sees a user and lets them into `/onboarding`.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type");
  // Where to go once the session exists. Constrained to a path on this origin:
  // an attacker-supplied absolute URL here would turn a confirmation link into
  // an open redirect carrying a freshly minted session.
  const requested = searchParams.get("next") ?? "/onboarding";
  const next = requested.startsWith("/") && !requested.startsWith("//") ? requested : "/onboarding";

  const supabase = await createClient();

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(`${origin}${next}`);
    return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(error.message)}`);
  }

  if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({
      type: type as "signup" | "email" | "recovery" | "invite" | "email_change",
      token_hash: tokenHash,
    });
    if (!error) return NextResponse.redirect(`${origin}${next}`);
    return NextResponse.redirect(`${origin}/login?error=${encodeURIComponent(error.message)}`);
  }

  // No code and no token. Usually a link that has already been used — Supabase
  // codes are single-use — or one that expired. Say that, rather than dropping
  // them on a login form with no explanation for why they are still signed out.
  return NextResponse.redirect(
    `${origin}/login?error=${encodeURIComponent(
      "That confirmation link has expired or was already used. Sign in, or sign up again.",
    )}`,
  );
}
