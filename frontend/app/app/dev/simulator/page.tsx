import type { Metadata } from "next";
import { FlaskConical } from "lucide-react";

import { PageHeader } from "@/components/shell/PageHeader";
import { isLocal } from "@/lib/env";
import { createClient } from "@/lib/supabase/server";
import { SimulatorPanels } from "./SimulatorPanels";

export const metadata: Metadata = { title: "Simulator" };

/**
 * The simulator control panel.
 *
 * Gated twice, on purpose. This check decides whether the page renders; the
 * backend router's own `require_dev_environment` decides whether the endpoints
 * exist at all. Either alone would be a single point of failure for a surface
 * that manufactures financial events, and the backend one is the load-bearing
 * half — hiding a page does not close an API.
 *
 * The `dev` flag on user metadata is the escape hatch for a deployed demo
 * environment, where NEXT_PUBLIC_ENVIRONMENT is not "local" but a specific
 * account still needs to drive the scenarios.
 */
export default async function SimulatorPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const devUser = user?.user_metadata?.dev === true;

  if (!isLocal && !devUser) {
    return (
      <div className="flex flex-col items-center rounded-lg border border-hairline bg-elevated px-8 py-20 text-center">
        <FlaskConical className="size-16 text-ink-faint" strokeWidth={1} aria-hidden />
        <h1 className="mt-6 font-display text-xl font-semibold tracking-[-0.02em] text-ink">
          Not available in this environment
        </h1>
        <p className="mt-2 max-w-sm text-sm leading-relaxed text-ink-muted">
          The simulator manufactures payment events, so it only runs in development.
        </p>
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Simulator"
        subtitle="Development environment only — for testing scenarios and firing events"
      />
      <SimulatorPanels />
    </>
  );
}
