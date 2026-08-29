"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

import { HOVER_LIFT, LIST_ITEM, LIST_ITEM_STATIC, SPRING_SNAPPY } from "@/lib/motion";

interface LiftCardProps {
  children: ReactNode;
  className?: string;
  /**
   * Enter as part of a parent's stagger.
   *
   * Off by default: a card that is not inside a `motion` parent driving
   * `hidden`/`show` would be stuck at `hidden` — invisible — forever.
   */
  staggered?: boolean;
}

/**
 * The one hover a clickable surface gets: 2px up, one shadow step.
 *
 * Every card in the product that can be clicked wraps in this, which is the
 * only way the KPI tiles, the playbook grid and the case rows can feel like the
 * same product. The lift is small on purpose — 2px reads as the card
 * acknowledging the pointer; 8px reads as the card trying to leave.
 *
 * `boxShadow` is animated to `var(--shadow-md)`. Framer Motion resolves CSS
 * variables against the element's computed style before interpolating, so this
 * follows the theme rather than pinning one shadow for light and another for
 * dark — which is exactly what a literal here would have done.
 */
export function LiftCard({ children, className, staggered = false }: LiftCardProps) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <motion.div
      className={className}
      variants={staggered ? (prefersReducedMotion ? LIST_ITEM_STATIC : LIST_ITEM) : undefined}
      whileHover={prefersReducedMotion ? undefined : HOVER_LIFT}
      transition={prefersReducedMotion ? { duration: 0 } : SPRING_SNAPPY}
    >
      {children}
    </motion.div>
  );
}
