"use client";

/**
 * Success rate by bank and hour of day.
 *
 * The grid is here because the interesting fact about a payment instrument is
 * not its average — it is *when* it fails. HDFC cards at 10am and HDFC cards at
 * 11pm are different instruments with the same name, and a single number per
 * bank hides the entire finding.
 *
 * **Colour is a status scale, not a gradient.** Three reserved bands — healthy,
 * degraded, failing — with the shade inside a band carrying magnitude. Every
 * cell also has a tooltip and an `aria-label` with the exact rate and sample
 * size, so nothing is encoded in colour alone, and there is a legend naming the
 * bands. A cell with no reading is drawn as absent rather than as zero: "we did
 * not see this bank at 4am" and "this bank fails at 4am" are opposite claims.
 *
 * All colour comes from `--success` / `--warning` / `--danger` through
 * `color-mix`, so the grid re-tints correctly in dark mode with no second
 * palette to keep in agreement.
 */

import { useEffect, useState, useTransition } from "react";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { HeatmapCell, HeatmapResponse } from "@/lib/api/network";
import { fetchHeatmap } from "@/lib/api/network";
import { formatPercent } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

/** Band boundaries. Healthy at or above the first, failing below the second. */
const HEALTHY_FLOOR = 0.8;
const DEGRADED_FLOOR = 0.6;

const METHOD_LABELS: Record<string, string> = {
  upi: "UPI",
  card: "Card",
  netbanking: "Net banking",
  wallet: "Wallet",
  mandate: "Mandate",
};

const BANDS = [
  { token: "--success", label: "Healthy", hint: "80% and above" },
  { token: "--warning", label: "Degraded", hint: "60–80%" },
  { token: "--danger", label: "Failing", hint: "below 60%" },
] as const;

function bandFor(rate: number): (typeof BANDS)[number] {
  if (rate >= HEALTHY_FLOOR) return BANDS[0];
  if (rate >= DEGRADED_FLOOR) return BANDS[1];
  return BANDS[2];
}

/**
 * Cell fill: the band's hue, mixed towards the page surface by how far into the
 * band the rate sits. A flat fill per band would lose the difference between a
 * bank at 61% and one at 20%, which is the difference between a bad hour and an
 * outage.
 */
function fillFor(rate: number): string {
  const band = bandFor(rate);
  const depth =
    band === BANDS[0]
      ? 0.35 + 0.65 * Math.min(1, (rate - HEALTHY_FLOOR) / (1 - HEALTHY_FLOOR))
      : band === BANDS[1]
        ? 0.35 + 0.5 * ((rate - DEGRADED_FLOOR) / (HEALTHY_FLOOR - DEGRADED_FLOOR))
        : 0.45 + 0.55 * (1 - rate / DEGRADED_FLOOR);
  return `color-mix(in oklch, var(${band.token}) ${Math.round(depth * 100)}%, var(--bg-subtle))`;
}

function hourLabel(hour: number): string {
  if (hour === 0) return "12am";
  if (hour === 12) return "12pm";
  return hour < 12 ? `${hour}am` : `${hour - 12}pm`;
}

/**
 * One bank-hour.
 *
 * The tooltip is a real `Tooltip` rather than a `title` attribute so it can
 * carry three lines of structure and open on keyboard focus as well as hover.
 * Its content is portalled and mounts only while open, so a 24-column grid does
 * not pay for 120 popups it will never show — but the exact rate stays on the
 * cell's `aria-label` regardless, because a tooltip a screen reader has to open
 * is a tooltip most readers never hear.
 */
function Cell({ cell, bank, hour }: { cell: HeatmapCell | undefined; bank: string; hour: number }) {
  if (!cell) {
    return (
    <td className="p-px">
      <Tooltip>
        <TooltipTrigger
          render={
            <div
              className="h-9 w-full rounded-[4px] border border-dashed border-hairline"
              aria-label={`${bank} at ${hourLabel(hour)}: no data`}
            />
          }
        />
        <TooltipContent>
          {bank} · {hourLabel(hour)} — no readings
        </TooltipContent>
      </Tooltip>
    </td>
    );
  }

  const band = bandFor(cell.success_rate);
  return (
    <td className="p-px">
    <Tooltip>
      <TooltipTrigger
        render={
          <div
            className="h-9 w-full rounded-[4px]"
            style={{ background: fillFor(cell.success_rate) }}
            aria-label={`${bank} at ${hourLabel(hour)}: ${formatPercent(cell.success_rate)} success, ${band.label}, ${cell.sample_size} retries`}
          />
        }
      />
      <TooltipContent className="text-center">
        <span className="block font-medium">
          {bank} · {hourLabel(hour)}
        </span>
        <span className="block">
          {formatPercent(cell.success_rate)} over {cell.sample_size} retries
        </span>
        <span className="block opacity-70">{band.label}</span>
      </TooltipContent>
    </Tooltip>
    </td>
  );
}

interface NetworkHeatmapProps {
  initial: HeatmapResponse;
}

export function NetworkHeatmap({ initial }: NetworkHeatmapProps) {
  const [data, setData] = useState(initial);
  const [method, setMethod] = useState<string | null>(null);
  const [loading, startLoading] = useTransition();

  // The tab list comes from the *first* response, not the current one. Deriving
  // it from the filtered data would leave exactly one tab visible after the
  // first click, with no way back.
  const [methods] = useState(initial.methods);

  useEffect(() => {
    let cancelled = false;
    startLoading(() => {
    void fetchHeatmap(method ?? undefined)
      .then((next) => {
        if (!cancelled) setData(next);
      })
      .catch(() => {
        // Keep the current grid. A blank heatmap on a transient failure reads
        // as "the network went dark", which is a much stronger claim.
      });
    });
    return () => {
    cancelled = true;
    };
  }, [method]);

  const byCell = new Map(data.cells.map((cell) => [`${cell.bank}:${cell.hour}`, cell]));

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
          Success rate by bank and hour
        </h2>
        {methods.length > 1 ? (
          // shadcn Tabs rather than hand-rolled role="tablist" buttons: arrow-key
          // roving focus, the correct aria wiring and the active indicator all
          // come with it, and none of the three were here before.
          <Tabs
            value={method ?? "all"}
            onValueChange={(next) => setMethod(next === "all" ? null : String(next))}
          >
            <TabsList>
              {[null, ...methods].map((value) => (
                <TabsTrigger key={value ?? "all"} value={value ?? "all"}>
                  {value === null ? "All" : (METHOD_LABELS[value] ?? value.toUpperCase())}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        ) : null}
      </div>

      <div
        className={cn(
          "relative overflow-x-auto rounded-card border border-hairline bg-elevated p-3 shadow-card transition-opacity",
          loading && "opacity-60",
        )}
      >
        {data.is_sparse ? (
          <p
            className="pointer-events-none absolute inset-x-0 top-1/2 -translate-y-1/2 text-center text-xs font-medium tracking-[0.06em] text-ink-faint uppercase opacity-50"
            aria-hidden
          >
            Indicative — thin samples
          </p>
        ) : null}

        <table className="w-full min-w-[720px] border-separate border-spacing-0">
          <caption className="sr-only">
            Payment success rate for each bank at each hour of the day, IST.
          </caption>
          <thead>
            <tr>
              <th scope="col" className="w-16" />
              {data.hours.map((hour) => (
                <th
                  key={hour}
                  scope="col"
                  className="pb-1 text-center font-mono text-[9px] font-normal text-ink-faint"
                >
                  {/* Every third hour, so the axis stays readable at this density. */}
                  {hour % 3 === 0 ? hour : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.banks.map((bank) => (
              <tr key={bank}>
                <th
                  scope="row"
                  className="pr-2 text-right font-mono text-[10px] font-normal whitespace-nowrap text-ink-muted"
                >
                  {bank}
                </th>
                {data.hours.map((hour) => (
                  <Cell
                    key={hour}
                    cell={byCell.get(`${bank}:${hour}`)}
                    bank={bank}
                    hour={hour}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-ink-faint">
        {BANDS.map((band) => (
          <span key={band.label} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className="size-2.5 rounded-[2px]"
              style={{ background: `color-mix(in oklch, var(${band.token}) 70%, var(--bg-subtle))` }}
            />
            {band.label} <span className="opacity-70">({band.hint})</span>
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-[2px] border border-dashed border-hairline" />
          No readings
        </span>
        <span className="ml-auto">Hours are IST.</span>
      </div>
    </section>
  );
}
