"use client";

/**
 * Manufacture an outage, to watch the rest of the page react to it.
 *
 * Hidden outside a local environment, and the simulator router 404s outside one
 * regardless — the same double gate the uplift seeder uses, for the same reason:
 * writing a fabricated outage into a real network would pause retries for every
 * merchant on it.
 *
 * The two actions update the page by different routes, and the asymmetry is
 * deliberate. Seeding calls `router.refresh()`, because the heatmap is
 * server-rendered and there is no channel a grid arrives on. Triggering an
 * outage does not, because the banner is subscribed to the same Redis channel
 * the endpoint publishes on — a refresh would produce the same visual result
 * while proving nothing about the live path.
 */

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { CloudOff, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import type { DowntimeRequest } from "@/lib/api/network";
import { seedNetworkStats, triggerDowntime } from "@/lib/api/network";

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
  const router = useRouter();
  const [running, setRunning] = useState<string | null>(null);
  const [refreshing, startTransition] = useTransition();

  async function seed() {
    setRunning("seed");
    try {
      const result = await seedNetworkStats();
      toast.success("Heatmap populated", {
        description: `${result.rows} readings across ${result.instruments} rails over ${result.days} days.`,
      });
      // The grid is server-rendered, unlike the banner — so this one *does*
      // need a refresh. There is no channel a heatmap arrives on.
      startTransition(() => router.refresh());
    } catch (error) {
      toast.error("Could not seed network stats", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
    } finally {
      setRunning(null);
    }
  }

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
        Simulator
      </h2>
      <p className="mt-1 text-xs text-ink-muted">
        Development only. The seeder fills the grid with a week of plausible behaviour; an
        outage writes the same alert a real detection writes, so the banner above updates over
        its live connection and the guardrail starts blocking retries.
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={running !== null || refreshing}
          onClick={seed}
        >
          {running === "seed" || refreshing ? (
            <Spinner className="size-3.5" />
          ) : (
            <Sparkles size={14} />
          )}
          Seed a week of network data
        </Button>

        {SCENARIOS.map((scenario) => (
          <Button
            key={scenario.id}
            variant="outline"
            size="sm"
            disabled={running !== null || refreshing}
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
