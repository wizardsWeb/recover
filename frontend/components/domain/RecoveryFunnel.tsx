"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useId } from "react";

import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import type { FunnelStage } from "@/lib/domain/funnel";

const WIDTH = 800;
const HEIGHT = 200;
const CENTER = HEIGHT / 2;
/** Half-height of the mouth. The tail is whatever proportion survives. */
const MOUTH = 78;

/**
 * The four stages of a case, as a narrowing shape.
 *
 * Drawn as one polygon rather than four bars because the *loss between* stages
 * is the thing worth looking at, and a bar chart puts that information in the
 * gaps between bars where nobody reads it. A funnel puts it in the slope.
 *
 * Heights are proportional to the first stage, so the shape cannot flatter the
 * numbers: a product recovering 8% of what it opens draws a spike, and no
 * choice of axis can make that look like a gentle taper.
 *
 * The reveal is a clip rectangle widening left to right, not a `pathLength`
 * stroke. `pathLength` draws an outline, and this shape's meaning is its area —
 * an outline that arrives before its fill reads as a diagram loading rather
 * than as flow through a pipe.
 */
export function RecoveryFunnel({ stages }: { stages: FunnelStage[] }) {
  const gradientId = useId();
  const clipId = useId();
  const prefersReducedMotion = useReducedMotion();

  const opened = stages[0]?.count ?? 0;
  // A merchant with no cases gets no funnel; the empty state upstream says so
  // in words. Drawing a zero-height sliver would be a shape claiming to mean
  // something.
  if (opened === 0) return null;

  const step = WIDTH / (stages.length - 1);
  const halfHeights = stages.map((stage) => Math.max((stage.count / opened) * MOUTH, 1.5));

  const top = halfHeights.map((half, index) => `${index * step},${CENTER - half}`);
  const bottom = halfHeights
    .map((half, index) => `${index * step},${CENTER + half}`)
    .reverse();
  const points = [...top, ...bottom].join(" ");

  return (
    <figure>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-auto w-full"
        role="img"
        aria-label={stages.map((stage) => `${stage.label}: ${stage.count}`).join(", ")}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--brand)" />
            <stop offset="100%" stopColor="var(--success)" />
          </linearGradient>
          <clipPath id={clipId}>
            <motion.rect
              x="0"
              y="0"
              height={HEIGHT}
              initial={{ width: prefersReducedMotion ? WIDTH : 0 }}
              whileInView={{ width: WIDTH }}
              viewport={{ once: true, amount: 0.4 }}
              transition={prefersReducedMotion ? { duration: 0 } : { duration: 1, ease: "easeOut" }}
            />
          </clipPath>
        </defs>

        <polygon points={points} fill={`url(#${gradientId})`} clipPath={`url(#${clipId})`} />

        {/* The stage boundaries. Hairlines rather than full-height rules: they
            are there to say where a stage ends, not to divide the shape into
            four charts. */}
        {halfHeights.slice(1, -1).map((half, index) => (
          <line
            key={stages[index + 1].label}
            x1={(index + 1) * step}
            x2={(index + 1) * step}
            y1={CENTER - half}
            y2={CENTER + half}
            stroke="var(--bg-elevated)"
            strokeWidth="2"
            clipPath={`url(#${clipId})`}
          />
        ))}
      </svg>

      <figcaption className="mt-3 grid grid-cols-4 gap-2">
        {stages.map((stage) => (
          <div key={stage.label} className="text-center">
            <p className="font-display text-xl font-semibold text-ink tabular-nums">
              <AnimatedNumber value={stage.count} startOnView />
            </p>
            <p className="mt-0.5 text-[11px] font-medium tracking-[0.06em] text-ink-faint uppercase">
              {stage.label}
            </p>
          </div>
        ))}
      </figcaption>
    </figure>
  );
}
