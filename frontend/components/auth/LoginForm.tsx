"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useHydrated } from "@/hooks/use-hydrated";
import { createClient } from "@/lib/supabase/client";

interface LoginFormProps {
  /** Where to land after signing in — set by the proxy guard on redirect. */
  next: string;
}

export function LoginForm({ next }: LoginFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  // `onSubmit` is the only thing stopping this form from submitting itself, and
  // it does not exist until React attaches. A click landing in that window gets
  // the browser's default instead: a GET to this same page with every field in
  // the query string, password included — visible in the URL bar, kept in
  // history, and written to the access log of every hop it passes through.
  // Disabling the button until hydration closes the window; the form is
  // unusable for those few hundred milliseconds either way.
  const hydrated = useHydrated();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);

    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      setPending(false);
      toast.error("Could not sign in", { description: error.message });
      return;
    }

    // The session cookie was just written by the browser client, but the server
    // components already rendered without it. refresh() re-runs them so the app
    // layout sees the session instead of bouncing straight back to /login.
    router.replace(next);
    router.refresh();
  }

  return (
    // Fields slide in from the left, 60ms apart. The order is the order they
    // will be filled in, so the cascade reads as the form arriving rather than
    // as decoration — and `StaggeredItem` drops the transform entirely under
    // reduced motion.
    <form onSubmit={onSubmit} className="grid gap-4">
      <div className="grid gap-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>

      <div className="mt-2">
        <Button type="submit" disabled={!hydrated || pending} className="w-full">
          {pending ? "Signing in…" : "Sign in"}
        </Button>
      </div>
    </form>
  );
}
