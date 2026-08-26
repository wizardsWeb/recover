import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { AuthCard } from "@/components/auth/AuthCard";
import { OnboardingForm } from "@/components/auth/OnboardingForm";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Set up your account" };

export default async function OnboardingPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  // The proxy already guards this route; this is the belt to its braces, and it
  // is also what narrows `user` for TypeScript.
  if (!user) redirect("/login");

  const { data: merchant } = await supabase
    .from("merchants")
    .select("name, onboarded")
    .eq("id", user.id)
    .maybeSingle();

  if (merchant?.onboarded) redirect("/app");

  return (
    <AuthCard title="Set up your account" description="Two questions, then you are in.">
      <OnboardingForm initialName={merchant?.name ?? ""} />
    </AuthCard>
  );
}
