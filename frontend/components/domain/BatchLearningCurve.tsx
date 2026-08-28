"use client";

/**
 * Recovery rate as the bandit accumulates evidence, against a fixed rule.
 *
 * Replaces the pre-computed chart this page carried through Phase 6, which drew
 * a recorded curve from a fixture. A learning curve is a claim about an
 * algorithm, and a fixture cannot be wrong — so it could not be evidence
 * either. This one is fed by a run that just happened.
 *
 * **Colour.** Bandit is `--brand`; the baseline is `--ink-blue`, not the muted
 * grey it might seem to deserve. Against this design system's gold, that grey
 * measures ΔE 8.0 for *normal* colour vision — below the readability floor,
 * before considering colour-vision deficiency at all. Identity never rests on
 * colour regardless: both series carry a legend entry and a direct label at the
 * right-hand end, the baseline is dashed, and the whole series is available as
 * a table.
 *
 * **The axis is fixed to the run's size from the first frame.** Letting it grow
 * with the data would have the lines crawl along a stretching x-axis during a
 * live run, which reads as the chart being redrawn rather than the run
 * progressing.
 */

import { useState } from "react";
import {
  CartesianGrid,
  Label,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { BatchWindow } from "@/lib/api/batch";
import { formatPercent } from "@/lib/utils/format";

const BANDIT_COLOR = "var(--brand)";
const BASELINE_COLOR = "var(--ink-blue)";

interface BatchLearningCurveProps {
  series: BatchWindow[];
  /** Total cases the run will play, so the axis does not stretch as it fills. */
  totalCases: number;
  /** Case number to annotate as the crossover. Zero draws no line. */
  convergenceCase?: number;
  /** Dims the plot while more data is still arriving. */
  live?: boolean;
}

interface Point {
  cases: number;
  bandit: number;
  baseline: number;
}

function CurveTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { dataKey?: string | number; value?: number | string }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  const read = (key: string) => payload.find((entry) => entry.dataKey === key)?.value;

  return (
    <div className="rounded-lg border border-hairline bg-elevated px-3 py-2 shadow-sm">
      <div className="mb-1 font-mono text-[10px] text-ink-faint">after {label} cases</div>
      <div className="space-y-0.5 text-xs">
        {[
          { key: "bandit", name: "Bandit", color: BANDIT_COLOR },
          { key: "baseline", name: "Fixed rule", color: BASELINE_COLOR },
        ].map((series) => (
          <div key={series.key} className="flex items-center gap-2">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: series.color }}
            />
            <span className="text-ink-muted">{series.name}</span>
            <span className="ml-auto font-mono tabular-nums text-ink">{read(series.key)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LegendSwatch({ dashed, color, label }: { dashed?: boolean; color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs">
      <span
        className="inline-block h-0.5 w-4 rounded-4xl"
        style={
          dashed
            ? {
                backgroundImage: `repeating-linear-gradient(to right, ${color} 0 4px, transparent 4px 7px)`,
              }
            : { background: color }
        }
      />
      <span className="text-ink-muted">{label}</span>
    </span>
  );
}

export function BatchLearningCurve({
  series,
  totalCases,
  convergenceCase = 0,
  live = false,
}: BatchLearningCurveProps) {
  const [showTable, setShowTable] = useState(false);

  const data: Point[] = series.map((window) => ({
    cases: window.cases,
    bandit: Math.round(window.bandit_rate * 1000) / 10,
    baseline: Math.round(window.baseline_rate * 1000) / 10,
  }));

  const last = data.at(-1);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <LegendSwatch color={BANDIT_COLOR} label="Contextual bandit" />
        <LegendSwatch color={BASELINE_COLOR} label="Fixed rule (baseline)" dashed />
        <button
          type="button"
          onClick={() => setShowTable((open) => !open)}
          className="ml-auto rounded-4xl border border-hairline px-2 py-0.5 text-[10px] text-ink-muted transition-colors hover:bg-subtle"
          aria-expanded={showTable}
        >
          {showTable ? "Hide data" : "View as table"}
        </button>
      </div>

      <div className={`h-[320px] w-full transition-opacity ${live ? "opacity-90" : ""}`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 16, right: 84, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="cases"
              type="number"
              domain={[0, totalCases]}
              tick={{ fill: "var(--text-tertiary)", fontSize: 11 }}
              stroke="var(--border-subtle)"
              label={{
                value: "cases seen",
                position: "insideBottomRight",
                offset: -4,
                fill: "var(--text-tertiary)",
                fontSize: 11,
              }}
            />
            <YAxis
              domain={[0, "dataMax + 8"]}
              tickFormatter={(value: number) => `${value}%`}
              tick={{ fill: "var(--text-tertiary)", fontSize: 11 }}
              stroke="var(--border-subtle)"
              width={44}
            />
            <Tooltip
              content={<CurveTooltip />}
              cursor={{ stroke: "var(--border-strong)", strokeDasharray: "3 3" }}
            />

            {convergenceCase > 0 ? (
              <ReferenceLine
                x={convergenceCase}
                stroke="var(--border-strong)"
                strokeDasharray="4 4"
              >
                <Label
                  value="Bandit surpasses baseline"
                  position="insideTopLeft"
                  fill="var(--text-tertiary)"
                  fontSize={10}
                  offset={8}
                />
              </ReferenceLine>
            ) : null}

            <Line
              type="monotone"
              dataKey="baseline"
              stroke={BASELINE_COLOR}
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              // Animation off: the data arrives in windows during a live run, so
              // each update would restart a 300ms redraw and the line would
              // pulse rather than extend.
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="bandit"
              stroke={BANDIT_COLOR}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {last ? (
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-ink-muted">
          <span>
            Bandit, latest window:{" "}
            <strong className="font-mono font-medium text-ink">{last.bandit}%</strong>
          </span>
          <span>
            Fixed rule:{" "}
            <strong className="font-mono font-medium text-ink">{last.baseline}%</strong>
          </span>
        </div>
      ) : null}

      {showTable ? (
        <div className="max-h-64 overflow-y-auto rounded-lg border border-hairline">
          <table className="w-full text-xs">
            <caption className="sr-only">
              Recovery rate per 50-case window, for both policies.
            </caption>
            <thead className="sticky top-0 bg-elevated">
              <tr className="border-b border-hairline text-ink-faint">
                <th scope="col" className="px-3 py-1.5 text-left font-medium">
                  Cases
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">
                  Bandit
                </th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">
                  Fixed rule
                </th>
              </tr>
            </thead>
            <tbody>
              {series.map((window) => (
                <tr key={window.cases} className="border-b border-hairline last:border-0">
                  <td className="px-3 py-1 font-mono tabular-nums text-ink-muted">
                    {window.cases}
                  </td>
                  <td className="px-3 py-1 text-right font-mono tabular-nums text-ink">
                    {formatPercent(window.bandit_rate)}
                  </td>
                  <td className="px-3 py-1 text-right font-mono tabular-nums text-ink-muted">
                    {formatPercent(window.baseline_rate)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
