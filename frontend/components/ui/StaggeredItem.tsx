"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

interface StaggeredItemProps {
  /** Position in the list. Drives the delay. */
  index: number;
  children: ReactNode;
  className?: string;
  /** Seconds added per item. */
  stagger?: number;
  /**
   * Ceiling on the computed delay, in seconds.
   *
   * Without it a long list punishes its own length: the audit log renders a
   * hundred rows, and an uncapped 0.04s step would leave the last one waiting
   * four seconds to exist. Clamping makes the cascade read at the top of the
   * list and everything below the fold simply be there.
   */
  maxDelay?: number;
  /** Horizontal offset, in px, to slide in from. */
  distance?: number;
}

/**
 * One item of a list that enters with a stagger.
 *
 * Motion is skipped outright when the reader has asked for reduced motion —
 * `useReducedMotion` resolves to the same value on server and client, so both
 * branches hydrate cleanly.
 *
 * Only `opacity` and `transform` are animated. Both are compositor properties,
 * so a long list stays at 60fps; animating height or margin here would relayout
 * the page once per item per frame.
 */
export function StaggeredItem({
  index,
  children,
  className,
  stagger = 0.06,
  maxDelay = 0.4,
  distance = -8,
}: StaggeredItemProps) {
  const prefersReducedMotion = useReducedMotion();

  if (prefersReducedMotion) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, x: distance }}
      animate={{ opacity: 1, x: 0 }}
      transition={{
        delay: Math.min(index * stagger, maxDelay),
        duration: 0.25,
        ease: "easeOut",
      }}
    >
      {children}
    </motion.div>
  );
}
