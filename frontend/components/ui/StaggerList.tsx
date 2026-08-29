"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

import { LIST_ITEM, LIST_ITEM_SCALE, LIST_ITEM_STATIC, listVariants } from "@/lib/motion";

interface StaggerListProps {
  children: ReactNode;
  className?: string;
  stagger?: number;
  /** The element to render. A grid of cards is a `ul`, a card body is a `div`. */
  as?: "div" | "ul" | "tbody";
}

/**
 * The parent half of a staggered list: it schedules its children and draws
 * nothing itself.
 *
 * `whileInView` with `once: true` rather than `animate`, because most of these
 * lists start below the fold. A list that finished its cascade while it was off
 * screen is, to the reader who scrolls to it, just a list — and replaying it on
 * every scroll back up would read as the data reloading.
 */
export function StaggerList({ children, className, stagger = 0.05, as = "div" }: StaggerListProps) {
  const prefersReducedMotion = useReducedMotion();
  const Component = motion[as];

  return (
    <Component
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.1 }}
      variants={listVariants(prefersReducedMotion ? 0 : stagger)}
    >
      {children}
    </Component>
  );
}

/**
 * One row of a `StaggerList`.
 *
 * `effect` picks how it arrives: `rise` for anything read as a list, `scale`
 * for a card grid. Both collapse to a plain fade under reduced motion.
 */
export function StaggerItem({
  children,
  className,
  as = "div",
  effect = "rise",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "li" | "tr";
  effect?: "rise" | "scale";
}) {
  const prefersReducedMotion = useReducedMotion();
  const Component = motion[as];
  const variants = prefersReducedMotion
    ? LIST_ITEM_STATIC
    : effect === "scale"
      ? LIST_ITEM_SCALE
      : LIST_ITEM;

  return (
    <Component className={className} variants={variants}>
      {children}
    </Component>
  );
}
