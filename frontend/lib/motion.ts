/**
 * The motion budget, in one place.
 *
 * Every animated element in the product reaches for a constant from here rather
 * than writing its own numbers inline. That is not tidiness — it is the only way
 * a hover on a KPI card and a hover on a case row feel like the same product.
 * Two springs tuned three points apart read as a bug nobody can name.
 *
 * Three springs, and that is the whole vocabulary:
 *
 *   * `SPRING` — the default. Entrances, expansions, anything that travels.
 *   * `SPRING_SNAPPY` — hover lifts. Stiffer, because a card that takes 300ms
 *     to acknowledge the pointer feels broken rather than smooth.
 *   * `SPRING_NUDGE` — the sidebar's 3px shift. Stiffest of the three: the
 *     distance is tiny, so the same stiffness as a card lift would make it
 *     drift rather than snap.
 *
 * Shadows are written as `var(--shadow-md)`. Framer Motion resolves CSS
 * variables against the element's computed style before animating, so the lift
 * follows the theme instead of hard-coding one shadow for light and another for
 * dark.
 */
import type { Target, Transition, Variants } from "framer-motion";

export const SPRING: Transition = { type: "spring", stiffness: 300, damping: 25 };
export const SPRING_SNAPPY: Transition = { type: "spring", stiffness: 400, damping: 25 };
export const SPRING_NUDGE: Transition = { type: "spring", stiffness: 500, damping: 30 };

/** The one hover a clickable card gets. */
export const HOVER_LIFT: Target = { y: -2, boxShadow: "var(--shadow-md)" };

/** The sidebar's nav items, which shift rather than lift. */
export const HOVER_NUDGE: Target = { x: 3 };

/** Every button, everywhere. */
export const TAP: Target = { scale: 0.97 };

/** Wrapped around a page's content by `PageTransition`. */
export const PAGE_ENTER = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.3, ease: "easeOut" },
} as const;

/**
 * Parent/child pair for a staggered list.
 *
 * The parent carries no visual change of its own — it exists only to schedule
 * its children, which is why `hidden`/`show` on it are empty objects.
 */
export function listVariants(stagger = 0.05): Variants {
  return {
    hidden: {},
    show: { transition: { staggerChildren: stagger } },
  };
}

export const LIST_ITEM: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0 },
};

/**
 * The card-grid variant: cards grow into place rather than sliding up.
 *
 * A 3% scale rather than an 8px rise, because a grid staggers in two dimensions
 * — a uniform upward slide across a 2×2 makes the second row look like it is
 * chasing the first, where a scale has no direction to disagree about.
 */
export const LIST_ITEM_SCALE: Variants = {
  hidden: { opacity: 0, scale: 0.97 },
  show: { opacity: 1, scale: 1 },
};

/**
 * The reduced-motion forms of everything above.
 *
 * `prefers-reduced-motion` does not mean "no feedback" — it means no travel.
 * Opacity is left alone (it moves nothing across the retina, which is the thing
 * the setting exists to stop) and every transform and duration is dropped, so a
 * hover still confirms the pointer landed and a list still appears.
 */
export const NO_MOTION: Transition = { duration: 0 };
export const NO_TRANSFORM: Target = {};
export const LIST_ITEM_STATIC: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1 },
};
