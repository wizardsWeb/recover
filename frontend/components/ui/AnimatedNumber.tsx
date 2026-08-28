"use client";

import {
  animate,
  motion,
  useInView,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "framer-motion";
import { useEffect, useRef } from "react";

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
  /**
   * Hold at zero until the number is scrolled into view, then count.
   *
   * For a figure below the fold: a stat that finished counting while it was off
   * screen is, to the reader who scrolls down to it, just a static number.
   */
  startOnView?: boolean;
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
  startOnView = false,
}: AnimatedNumberProps) {
  const motionValue = useMotionValue(0);
  const text = useTransform(motionValue, format);
  const prefersReducedMotion = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  // `once` so scrolling back past the figure does not replay the count, which
  // would read as the value changing rather than as the page repeating itself.
  const inView = useInView(ref, { once: true, amount: 0.6 });
  const shouldRun = !startOnView || inView;

  useEffect(() => {
    if (!shouldRun) return;
    if (prefersReducedMotion) {
      motionValue.set(value);
      return;
    }
    const controls = animate(motionValue, value, { duration, ease: "easeOut" });
    return () => controls.stop();
  }, [value, duration, motionValue, prefersReducedMotion, shouldRun]);

  return (
    <span ref={ref} className={className}>
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
  startOnView,
}: Omit<AnimatedNumberProps, "format">) {
  return (
    <AnimatedNumber
      value={value}
      duration={duration}
      className={className}
      startOnView={startOnView}
      format={(n) => formatINR(Math.round(n))}
    />
  );
}

/** `AnimatedNumber` for a 0-1 rate, rendered as a percentage. */
export function AnimatedPercent({
  value,
  duration,
  className,
  startOnView,
  fractionDigits = 1,
}: Omit<AnimatedNumberProps, "format"> & { fractionDigits?: number }) {
  return (
    <AnimatedNumber
      value={value}
      duration={duration}
      className={className}
      startOnView={startOnView}
      format={(n) => `${(n * 100).toFixed(fractionDigits)}%`}
    />
  );
}
