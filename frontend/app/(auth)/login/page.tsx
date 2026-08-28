import type { Metadata } from "next";
import Link from "next/link";

import { AuthCard } from "@/components/auth/AuthCard";
import { LoginForm } from "@/components/auth/LoginForm";

export const metadata: Metadata = { title: "Sign in" };

/**
 * Server component so `next` can be read from the URL without pulling
 * `useSearchParams` — and its Suspense boundary — into the client.
 */
export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const params = await searchParams;
  const requested = params.next;
  // Only same-origin paths, never an absolute URL — an attacker-supplied
  // `?next=https://evil.example` would otherwise turn login into an open redirect.
  const next =
    typeof requested === "string" && requested.startsWith("/") && !requested.startsWith("//")
      ? requested
      : "/app";

  // Set by `/auth/callback` when a confirmation or recovery link could not be
  // redeemed — most often an expired one, or one already used, since Supabase
  // codes are single-use. Rendering it is what turns "I clicked the link and
  // I am still signed out" into something the reader can act on.
  const error = typeof params.error === "string" ? params.error : null;

  return (
    <AuthCard
      title="Sign in"
      description="Welcome back."
      footer={
        <>
          Don&apos;t have an account?{" "}
          <Link href="/signup" className="font-medium text-brand underline-offset-4 hover:underline">
            Sign up
          </Link>
        </>
      }
    >
      {error ? (
        <p
          role="alert"
          className="mb-4 rounded-md border border-danger/30 bg-danger-subtle px-3 py-2 text-xs leading-relaxed text-danger"
        >
          {error}
        </p>
      ) : null}
      <LoginForm next={next} />
    </AuthCard>
  );
}
