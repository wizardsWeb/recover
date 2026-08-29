"use client";

/**
 * Manufacture a demo's worth of uplift history.
 *
 * Hidden outside a local environment, and the backend router it calls 404s
 * outside one too. Both gates matter: hiding the button would not stop a
 * fabricated recovery history being written into a real merchant's ledger by
 * anyone who found the endpoint, and gating only the backend would leave a
 * button that fails in a way nobody can explain on stage.
 *
 * `router.refresh()` rather than local state: the page is a Server Component
 * reading through the API, so re-running it on the server is what makes the new
 * numbers appear — and it is the same path a fresh page load takes, so there is
 * no second rendering of the ROI panel to keep in agreement.
 */

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { seedUpliftHistory } from "@/lib/api/roi";

export function SeedUpliftButton() {
  const router = useRouter();
  const [seeding, setSeeding] = useState(false);
  const [refreshing, startTransition] = useTransition();

  async function seed() {
    setSeeding(true);
    try {
      const result = await seedUpliftHistory();
      const trained = result.models.filter((model) => model.status === "trained").length;
      toast.success("Seeded uplift history", {
        description: `${result.treated} treated and ${result.controls} control cases; ${trained} of ${result.models.length} playbooks trained.`,
      });
      startTransition(() => router.refresh());
    } catch (error) {
      toast.error("Could not seed uplift history", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setSeeding(false);
    }
  }

  const busy = seeding || refreshing;

  return (
    <Button variant="outline" size="sm" onClick={seed} disabled={busy} className="print:hidden">
      <Sparkles aria-hidden />
      {/* The label carries the state. A spinner beside a label that already
          says "Seeding…" is the same fact twice. */}
      {busy ? "Seeding…" : "Seed demo data"}
    </Button>
  );
}
