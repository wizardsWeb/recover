"use client";

import { motion, useReducedMotion } from "framer-motion";

const SIZE = 80;
const STROKE = 8;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * One segment's recovery rate, as a ring — with the control rate inside it.
 *
 * Two arcs rather than two numbers because the comparison *is* the finding:
 * a segment recovering 62% against a 58% control and one recovering 62% against
 * 18% are the same headline number and completely different results. Nested
 * rings put the gap where the eye lands first.
 *
 * Drawn by animating `strokeDashoffset` from a full circumference down to the
 * arc's length. Rotated -90° so the arc starts at twelve o'clock, which is where
 * a reader assumes a dial begins.
 *
 * The figures are also written in the centre and in the `aria-label`, so nothing
 * here is encoded in arc length alone.
 */
export function BucketDonut({
  treated,
  control,
  harmful = false,
}: {
  /** 0-1. */
  treated: number;
  /** 0-1. */
  control: number;
  /** Lift is negative — the ring reads as a warning rather than a result. */
  harmful?: boolean;
}) {
  const prefersReducedMotion = useReducedMotion();
  const clamp = (value: number) => Math.min(1, Math.max(0, value));
  const treatedOffset = CIRCUMFERENCE * (1 - clamp(treated));
  const controlOffset = CIRCUMFERENCE * (1 - clamp(control));

  const transition = (delay: number) =>
    prefersReducedMotion ? { duration: 0 } : { duration: 0.9, ease: "easeOut" as const, delay };

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="size-20 shrink-0 -rotate-90"
      role="img"
      aria-label={`Treated ${Math.round(treated * 100)}% against a control of ${Math.round(control * 100)}%`}
    >
      <circle
        cx={SIZE / 2}
        cy={SIZE / 2}
        r={RADIUS}
        fill="none"
        stroke="var(--bg-inset)"
        strokeWidth={STROKE}
      />

      {/* Control first, so the treated arc draws over it. */}
      <motion.circle
        cx={SIZE / 2}
        cy={SIZE / 2}
        r={RADIUS - STROKE - 1}
        fill="none"
        stroke="var(--ink-400)"
        strokeWidth={2}
        strokeLinecap="round"
        strokeDasharray={CIRCUMFERENCE}
        initial={{ strokeDashoffset: prefersReducedMotion ? controlOffset : CIRCUMFERENCE }}
        whileInView={{ strokeDashoffset: controlOffset }}
        viewport={{ once: true, amount: 0.6 }}
        transition={transition(0.1)}
      />

      <motion.circle
        cx={SIZE / 2}
        cy={SIZE / 2}
        r={RADIUS}
        fill="none"
        stroke={harmful ? "var(--danger)" : "var(--brand)"}
        strokeWidth={STROKE}
        strokeLinecap="round"
        strokeDasharray={CIRCUMFERENCE}
        initial={{ strokeDashoffset: prefersReducedMotion ? treatedOffset : CIRCUMFERENCE }}
        whileInView={{ strokeDashoffset: treatedOffset }}
        viewport={{ once: true, amount: 0.6 }}
        transition={transition(0)}
      />

      {/* Counter-rotated so the text sits upright inside the rotated svg. */}
      <text
        x={SIZE / 2}
        y={SIZE / 2}
        textAnchor="middle"
        dominantBaseline="central"
        transform={`rotate(90 ${SIZE / 2} ${SIZE / 2})`}
        className="fill-[var(--text-primary)] font-mono text-[15px] font-medium"
      >
        {Math.round(treated * 100)}%
      </text>
    </svg>
  );
}
