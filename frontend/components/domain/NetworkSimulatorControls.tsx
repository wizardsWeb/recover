"use client";

/**
 * Manufacture an outage, to watch the rest of the page react to it.
 *
 * Hidden outside a local environment, and the simulator router 404s outside one
 * regardless — the same double gate the uplift seeder uses, for the same reason:
 * writing a fabricated outage into a real network would pause retries for every
 * merchant on it.
 *
 * Nothing here refreshes the page. The alert banner is subscribed to the same
 * Redis channel the endpoint publishes on, so the banner updating on its own is
 * the thing being demonstrated — calling `router.refresh()` would produce the
 * same visual result while proving nothing.
 */

import { useState } from "react";
import { CloudOff } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { DowntimeRequest } from "@/lib/api/network";
import { triggerDowntime } from "@/lib/api/network";

const SCENARIOS: Array<{ id: string; label: string; payload: DowntimeRequest }> = [
  {
    id: "b3",
    label: "SBI UPI downtime (30 min)",
    payload: { bank: "SBI", method: "upi", severity: "high", durationMinutes: 30 },
  },
  {
    id: "hdfc",
    label: "HDFC card degradation (15 min)",
    payload: { bank: "HDFC", method: "card", severity: "medium", durationMinutes: 15 },
  },
];

export function NetworkSimulatorControls() {
  const [running, setRunning] = useState<string | null>(null);

  async function fire(id: string, payload: DowntimeRequest) {
    setRunning(id);
    try {
      const result = await triggerDowntime(payload);
      toast.success(`${result.bank} ${result.method.toUpperCase()} is now degraded`, {
        description: `Success rate dropped to ${Math.round(result.successRate * 100)}%. Retries into it are blocked until it lifts.`,
      });
    } catch (error) {
      toast.error("Could not start the outage", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setRunning(null);
    }
  }

  return (
    <section className="rounded-lg border border-dashed border-hairline p-4 print:hidden">
      <h2 className="flex items-center gap-2 text-sm font-medium text-ink">
        <CloudOff size={14} className="text-ink-faint" aria-hidden />
        Simulate an outage
      </h2>
      <p className="mt-1 text-xs text-ink-muted">
        Development only. Writes the same alert a real detection writes, so the banner above
        updates over its live connection and the guardrail starts blocking retries.
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        {SCENARIOS.map((scenario) => (
          <Button
            key={scenario.id}
            variant="outline"
            size="sm"
            disabled={running !== null}
            onClick={() => fire(scenario.id, scenario.payload)}
          >
            {running === scenario.id ? <Spinner className="size-3.5" /> : null}
            {scenario.label}
          </Button>
        ))}
      </div>
    </section>
  );
}
