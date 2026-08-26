import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/shell/AppShell";
import { SIDEBAR_COOKIE } from "@/components/shell/Sidebar";
import { isLocal } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";

/**
 * The guarded shell.
 *
 * proxy.ts already turns anonymous requests away, but the session is read again
 * here because this layout needs the user anyway — and an authorisation
 * decision should not rest on a single check running in a different process.
 */
export default async function AppLayout({ children }: LayoutProps<"/app">) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const { data: merchant } = await supabase
    .from("merchants")
    .select("name, onboarded")
    .eq("id", user.id)
    .maybeSingle();

  if (!merchant?.onboarded) redirect("/onboarding");

  // Reading the collapse preference here is what lets the first HTML come back
  // at the right width, instead of flashing open and snapping shut.
  const cookieStore = await cookies();
  const defaultSidebarCollapsed = cookieStore.get(SIDEBAR_COOKIE)?.value === "true";

  return (
    <AppShell
      email={user.email ?? ""}
      businessName={merchant.name}
      showDevTools={isLocal}
      defaultSidebarCollapsed={defaultSidebarCollapsed}
    >
      {children}
    </AppShell>
  );
}
