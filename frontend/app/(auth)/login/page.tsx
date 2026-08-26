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
      <LoginForm next={next} />
    </AuthCard>
  );
}
