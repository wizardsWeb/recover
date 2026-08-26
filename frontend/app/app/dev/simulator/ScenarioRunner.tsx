"use client";

import { ChevronRight, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { CodeBlock } from "@/components/ui/code-block";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Spinner } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api/client";
import { fireScenario, getFixtureStatus, type FixtureStatus, type ScenarioMeta } from "@/lib/api/simulator";
import { Panel, useSimulatorRefresh } from "./SimulatorPanels";

/** ₹ with thousands separators, from paise. */
function formatInr(cents: number | null): string {
  if (cents === null) return "—";
  return `₹${(cents / 100).toLocaleString("en-IN")}`;
}

function optionLabel(scenario: ScenarioMeta): string {
  const parts = [scenario.code];
  if (scenario.personaName) parts.push(scenario.personaName);
  if (scenario.playbook) parts.push(scenario.playbook.replace(/_/g, " "));
  const label = parts.join(" — ");
  if (scenario.deferred) return `${label} (coming in Phase 11)`;
  return scenario.amountAtRiskCents ? `${label} (${formatInr(scenario.amountAtRiskCents)})` : label;
}

export function ScenarioRunner() {
  const { token, refresh } = useSimulatorRefresh();
  const [status, setStatus] = useState<FixtureStatus | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [firing, setFiring] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function read() {
      try {
        const next = await getFixtureStatus();
        if (!cancelled) setStatus(next);
      } catch (error) {
        if (!cancelled) {
          toast.error(error instanceof ApiError ? error.message : "Could not load scenarios");
        }
      }
    }

    void read();
    return () => {
      cancelled = true;
    };
  }, [token]);

  // The default selection is derived, not stored. Writing "first scenario" into
  // state from an effect would mean a render with nothing selected followed by
  // a second one that fixes it; deriving it means the card is right on the
  // first paint after the catalogue lands.
  const activeCode = selected || status?.scenarios[0]?.code || "";

  const scenario = useMemo(
    () => status?.scenarios.find((item) => item.code === activeCode) ?? null,
    [status, activeCode],
  );

  async function onFire() {
    if (!scenario) return;
    setFiring(true);
    try {
      const result = await fireScenario(scenario.code);
      if (scenario.deferred) {
        toast.info(result.message);
      } else {
        const count = result.eventIds?.length ?? 1;
        toast.success(
          count > 1
            ? `Fired ${result.scenarioCode}: ${count} events created`
            : `Fired ${result.scenarioCode}: case ${result.caseId?.slice(0, 8)} created`,
        );
      }
      refresh();
    } catch (error) {
      if (error instanceof ApiError && error.status === 424) {
        toast.error("Load fixtures first", {
          description: "The personas this scenario needs have not been created yet.",
          action: {
            label: "Go load them",
            onClick: () => {
              document
                .getElementById("simulator-fixtures")
                ?.scrollIntoView({ behavior: "smooth", block: "center" });
            },
          },
        });
      } else {
        toast.error(error instanceof ApiError ? error.message : "Could not fire scenario");
      }
    } finally {
      setFiring(false);
    }
  }

  return (
    <Panel
      title="Scenario runner"
      description="Fire one of the nine scripted beats from scenarios.md"
    >
      <div className="space-y-4">
        <NativeSelect
          className="w-full max-w-xl"
          value={activeCode}
          onChange={(event) => setSelected(event.target.value)}
          aria-label="Scenario"
        >
          {(status?.scenarios ?? []).map((item) => (
            <NativeSelectOption key={item.code} value={item.code}>
              {optionLabel(item)}
            </NativeSelectOption>
          ))}
        </NativeSelect>

        {scenario && (
          <div className="rounded-md border border-hairline bg-subtle p-4">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="font-display text-base font-semibold text-ink">
                {scenario.personaName ?? scenario.code}
              </span>
              <span className="text-xs text-ink-muted">{scenario.merchantContext}</span>
            </div>

            <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs text-ink-faint">Playbook</dt>
                <dd className="font-mono text-xs text-ink">{scenario.playbook ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-xs text-ink-faint">Amount at risk</dt>
                <dd className="text-ink">{formatInr(scenario.amountAtRiskCents)}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs text-ink-faint">What happens</dt>
                <dd className="text-ink">{scenario.oneLineDescription}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs text-ink-faint">Expected agent path</dt>
                <dd className="text-ink-muted">{scenario.videoExpectedPath}</dd>
              </div>
            </dl>

            {scenario.samplePayload && (
              <details className="group/payload mt-4">
                <summary className="flex cursor-pointer list-none items-center gap-1 text-xs font-medium text-ink-muted hover:text-ink">
                  <ChevronRight
                    className="size-3 transition-transform group-open/payload:rotate-90"
                    strokeWidth={2}
                    aria-hidden
                  />
                  Event payload
                </summary>
                <CodeBlock value={scenario.samplePayload} className="mt-2" />
              </details>
            )}
          </div>
        )}

        <Button onClick={onFire} disabled={!scenario || firing || (!status?.loaded && !scenario?.deferred)}>
          {firing ? <Spinner /> : <Play className="size-4" strokeWidth={1.75} aria-hidden />}
          Fire scenario
        </Button>
      </div>
    </Panel>
  );
}
