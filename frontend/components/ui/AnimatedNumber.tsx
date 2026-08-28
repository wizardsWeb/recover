"use client";

import { animate, useMotionValue, useReducedMotion, useTransform, motion } from "framer-motion";
import { useEffect } from "react";

import { formatINR } from "@/lib/utils/format";

const PLAIN = new Intl.NumberFormat("en-IN");

export interface AnimatedNumberProps {
  /** The settled value. Changing it animates from wherever the number is now. */
  value: number;
  /** Renders the in-flight number. Called on every frame, so keep it cheap. */
  format?: (n: number) => string;
  /** Seconds. */
  duration?: number;
  className?: string;
}

/**
 * A number that counts up to `value`.
 *
 * The count is driven by a `MotionValue`, which writes straight to the DOM node
 * on each frame instead of re-rendering React. Two things follow from that, and
 * both are the reason this is not a `useState` counter:
 *
 * * A parent re-render cannot restart or flash the animation — the animation
 *   lives outside React's render output entirely. It restarts only when `value`
 *   itself changes, which is the effect's sole dependency.
 * * Repeated updates are cheap enough to point live data at, which is what the
 *   dashboard does once Realtime is subscribed.
 *
 * The count starts from wherever the number currently sits rather than from
 * zero, so a live update ticks 35 -> 41 instead of dropping to zero and
 * climbing back — a reset would read as the value having gone away.
 *
 * The animated span is hidden from assistive tech: a value mutating every frame
 * is noise to a screen reader. The settled figure is exposed beside it.
 */
export function AnimatedNumber({
  value,
  format = (n) => PLAIN.format(Math.round(n)),
  duration = 1.2,
  className,
}: AnimatedNumberProps) {
  const motionValue = useMotionValue(0);
  const text = useTransform(motionValue, format);
  const prefersReducedMotion = useReducedMotion();

  useEffect(() => {
    if (prefersReducedMotion) {
      motionValue.set(value);
      return;
    }
    const controls = animate(motionValue, value, { duration, ease: "easeOut" });
    return () => controls.stop();
  }, [value, duration, motionValue, prefersReducedMotion]);

  return (
    <span className={className}>
      <motion.span aria-hidden>{text}</motion.span>
      <span className="sr-only">{format(value)}</span>
    </span>
  );
}

/** `AnimatedNumber` for paise, rendered as rupees. */
export function AnimatedINR({
  value,
  duration,
  className,
}: Omit<AnimatedNumberProps, "format">) {
  return (
    <AnimatedNumber
      value={value}
      duration={duration}
      className={className}
      format={(n) => formatINR(Math.round(n))}
    />
  );
}

/** `AnimatedNumber` for a 0-1 rate, rendered as a percentage. */
export function AnimatedPercent({
  value,
  duration,
  className,
  fractionDigits = 1,
}: Omit<AnimatedNumberProps, "format"> & { fractionDigits?: number }) {
  return (
    <AnimatedNumber
      value={value}
      duration={duration}
      className={className}
      format={(n) => `${(n * 100).toFixed(fractionDigits)}%`}
    />
  );
}
