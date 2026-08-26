import type { Metadata } from "next";

import { PageHeader } from "@/components/shell/PageHeader";
import { FirstTimeDashboard } from "@/components/empty-states/FirstTimeDashboard";

export const metadata: Metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <>
      <PageHeader title="Dashboard" subtitle="Live view of recovery activity" />
      <FirstTimeDashboard />
    </>
  );
}
