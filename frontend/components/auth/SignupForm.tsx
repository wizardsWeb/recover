"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";

export function SignupForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [awaitingConfirmation, setAwaitingConfirmation] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);

    const supabase = createClient();
    const trimmed = name.trim();

    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      // Lands in raw_user_meta_data, which the on_auth_user_created trigger
      // reads to name the merchant row it creates. Onboarding can then
      // pre-fill instead of asking twice.
      options: trimmed ? { data: { name: trimmed } } : undefined,
    });

    if (error) {
      setPending(false);
      toast.error("Could not create account", { description: error.message });
      return;
    }

    if (!data.session) {
      // Email confirmation is on for this Supabase project. There is no session
      // to redirect with, so say so rather than pushing to a guarded route.
      setPending(false);
      setAwaitingConfirmation(true);
      return;
    }

    router.replace("/onboarding");
    router.refresh();
  }

  if (awaitingConfirmation) {
    return (
      <p className="text-sm leading-relaxed text-ink-muted">
        Check <span className="font-medium text-ink">{email}</span> for a confirmation link. Setup
        continues once the address is verified.
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-4">
      <div className="grid gap-2">
        <Label htmlFor="name">Business name</Label>
        <Input
          id="name"
          name="name"
          autoComplete="organization"
          placeholder="Optional"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </div>

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
          autoComplete="new-password"
          required
          minLength={8}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <p className="text-xs text-ink-faint">At least 8 characters.</p>
      </div>

      <Button type="submit" disabled={pending} className="mt-2 w-full">
        {pending ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
