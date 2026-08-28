"use client";

import { ChevronDown } from "lucide-react";
import { motion, useReducedMotion } from "framer-motion";

/**
 * The nudge that says the page continues.
 *
 * A full-viewport hero with no visible edge is a page a lot of readers assume
 * is the whole site. This is the cheapest possible fix for that.
 *
 * Held still under `prefers-reduced-motion`: a permanently bobbing element is
 * exactly the kind of thing that reading setting exists to stop, and the arrow
 * still says what it means without moving.
 */
export function ScrollCue() {
  const prefersReducedMotion = useReducedMotion();

  return (
    <a
      href="#how-it-works"
      aria-label="Skip to how it works"
      className="absolute inset-x-0 bottom-8 mx-auto flex w-fit rounded-full p-2 text-sidebar-gold transition-opacity duration-150 hover:opacity-70 focus-visible:ring-3 focus-visible:ring-white/40 focus-visible:outline-none"
    >
      <motion.span
        aria-hidden
        animate={prefersReducedMotion ? undefined : { y: [0, 6, 0] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
      >
        <ChevronDown className="size-6" strokeWidth={1.5} />
      </motion.span>
    </a>
  );
}
