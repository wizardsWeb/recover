"use client";

import { useState } from "react";
import {
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  BANDIT_CURVE,
  CROSSOVER_AT_CASE,
  CURVE_ANNOTATIONS,
  type CurvePoint,
} from "@/lib/data/bandit_curve_demo";

/**
 * Recovery rate as the bandit accumulates evidence, against a fixed rule.
 *
 * **Colour.** Bandit is `--brand`; the baseline is `--ink-blue`, not the muted
 * grey it might seem to deserve. Against this design system's gold, the muted
 * grey measures ΔE 8.0 for *normal* colour vision — below the readability floor,
 * before considering CVD at all. Two hues that actually separate is the only
 * version of this chart a reader can use.
 *
 * Identity never rests on colour alone regardless: both series carry a legend
 * entry and a direct label at the right-hand end, and the baseline is dashed.
 */

const BANDIT_COLOR = "var(--brand)";
const BASELINE_COLOR = "var(--ink-blue)";

function formatCases(value: number): string {
  return value === 0 ? "0" : `${value}`;
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

  const read = (key: string) =>
    payload.find((entry) => entry.dataKey === key)?.value;

  return (
    <div className="rounded-lg border border-hairline bg-elevated px-3 py-2 shadow-sm">
      <div className="mb-1 font-mono text-[10px] text-ink-faint">
        after {label} cases
      </div>
      <div className="space-y-0.5 text-xs">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: BANDIT_COLOR }}
          />
          <span className="text-ink-muted">Bandit</span>
          <span className="ml-auto font-mono tabular-nums text-ink">
            {read("bandit")}%
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ background: BASELINE_COLOR }}
          />
          <span className="text-ink-muted">Fixed rule</span>
          <span className="ml-auto font-mono tabular-nums text-ink">
            {read("baseline")}%
          </span>
        </div>
      </div>
    </div>
  );
}

/**
 * A direct label at the right-hand end of one line.
 *
 * Rendered only on the final point — a label on every point is noise. The text
 * wears an ink token rather than the series colour: the line it sits beside is
 * the coloured mark that carries identity, and coloured text would fail
 * contrast at this size.
 */
function EndLabel({
  x,
  y,
  index,
  text,
}: {
  x?: number;
  y?: number;
  index?: number;
  text: string;
}) {
  if (index !== BANDIT_CURVE.length - 1 || x == null || y == null) return null;
  return (
    <text
      x={x + 8}
      y={y}
      dy={4}
      fill="var(--text-secondary)"
      fontSize={11}
      textAnchor="start"
    >
      {text}
    </text>
  );
}

/** The annotation nearest a given x, so the dot and its note stay together. */
function nearestPoint(cases: number): CurvePoint {
  return BANDIT_CURVE.reduce((best, point) =>
    Math.abs(point.cases - cases) < Math.abs(best.cases - cases) ? point : best,
  );
}

export function BanditLearningCurve() {
  const [showTable, setShowTable] = useState(false);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-1.5 text-xs">
          <span
            className="inline-block h-0.5 w-4 rounded-4xl"
            style={{ background: BANDIT_COLOR }}
          />
          <span className="text-ink-muted">Contextual bandit</span>
        </span>
        <span className="flex items-center gap-1.5 text-xs">
          <span
            className="inline-block h-0.5 w-4 rounded-4xl"
            style={{
              backgroundImage: `repeating-linear-gradient(to right, ${BASELINE_COLOR} 0 4px, transparent 4px 7px)`,
            }}
          />
          <span className="text-ink-muted">Fixed rule (baseline)</span>
        </span>

        <button
          type="button"
          onClick={() => setShowTable((open) => !open)}
          className="ml-auto rounded-4xl border border-hairline px-2 py-0.5 text-[10px] text-ink-muted transition-colors hover:bg-subtle"
          aria-expanded={showTable}
        >
          {showTable ? "Hide data" : "View as table"}
        </button>
      </div>

      <div className="h-[320px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={BANDIT_CURVE}
            margin={{ top: 16, right: 76, bottom: 8, left: 0 }}
          >
            <CartesianGrid
              stroke="var(--border-subtle)"
              strokeDasharray="2 4"
              vertical={false}
            />
            <XAxis
              dataKey="cases"
              type="number"
              domain={[0, 1000]}
              tickFormatter={formatCases}
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
              domain={[15, 42]}
              tickFormatter={(v: number) => `${v}%`}
              tick={{ fill: "var(--text-tertiary)", fontSize: 11 }}
              stroke="var(--border-subtle)"
              width={44}
            />
            <Tooltip
              content={<CurveTooltip />}
              cursor={{ stroke: "var(--border-strong)", strokeDasharray: "3 3" }}
            />

            <ReferenceLine
              x={CROSSOVER_AT_CASE}
              stroke="var(--border-strong)"
              strokeDasharray="4 4"
              label={{
                value: "Bandit surpasses baseline",
                position: "top",
                fill: "var(--text-tertiary)",
                fontSize: 10,
              }}
            />

            {CURVE_ANNOTATIONS.map((note) => {
              const point = nearestPoint(note.cases);
              return (
                <ReferenceDot
                  key={note.cases}
                  x={point.cases}
                  y={point.bandit}
                  r={4}
                  fill={BANDIT_COLOR}
                  stroke="var(--bg-base)"
                  strokeWidth={2}
                />
              );
            })}

            <Line
              type="monotone"
              dataKey="baseline"
              stroke={BASELINE_COLOR}
              strokeWidth={2}
              strokeDasharray="5 4"
              dot={false}
              isAnimationActive={false}
            >
              <LabelList
                dataKey="baseline"
                content={<EndLabel text="rule" />}
              />
            </Line>
            <Line
              type="monotone"
              dataKey="bandit"
              stroke={BANDIT_COLOR}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            >
              <LabelList dataKey="bandit" content={<EndLabel text="bandit" />} />
            </Line>
          </LineChart>
        </ResponsiveContainer>
      </div>

      <ol className="space-y-1">
        {CURVE_ANNOTATIONS.map((note) => (
          <li key={note.cases} className="flex gap-2 text-xs text-ink-muted">
            <span className="font-mono text-[10px] text-ink-faint">
              ~{note.cases}
            </span>
            <span
              className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ background: BANDIT_COLOR }}
            />
            <span>{note.label}</span>
          </li>
        ))}
      </ol>

      {showTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <caption className="sr-only">
              Recovery rate by cases seen, contextual bandit versus fixed rule
            </caption>
            <thead>
              <tr className="border-b border-hairline text-ink-faint">
                <th scope="col" className="py-1 text-left font-medium">
                  Cases
                </th>
                <th scope="col" className="py-1 text-right font-medium">
                  Bandit
                </th>
                <th scope="col" className="py-1 text-right font-medium">
                  Fixed rule
                </th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums text-ink-muted">
              {BANDIT_CURVE.map((point) => (
                <tr key={point.cases} className="border-b border-hairline/50">
                  <td className="py-1">{point.cases}</td>
                  <td className="py-1 text-right">{point.bandit}%</td>
                  <td className="py-1 text-right">{point.baseline}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
