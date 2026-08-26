import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { PageHeader } from "@/components/shell/PageHeader";
import { ProfileForm } from "@/components/settings/ProfileForm";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Settings" };

export default async function SettingsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const { data: merchant } = await supabase
    .from("merchants")
    .select("name, vertical, timezone")
    .eq("id", user.id)
    .maybeSingle();

  if (!merchant) redirect("/onboarding");

  return (
    <>
      <PageHeader title="Settings" subtitle="Your business, and how the agent behaves on its behalf" />

      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          {/* Rendered disabled rather than hidden so the shape of what is
              coming is visible from the first session. */}
          <TabsTrigger value="playbooks" disabled>
            Playbooks
          </TabsTrigger>
          <TabsTrigger value="compliance" disabled>
            Compliance
          </TabsTrigger>
          <TabsTrigger value="team" disabled>
            Team
          </TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="pt-6">
          <ProfileForm
            initialName={merchant.name}
            initialVertical={merchant.vertical}
            initialTimezone={merchant.timezone}
          />
        </TabsContent>
      </Tabs>
    </>
  );
}
