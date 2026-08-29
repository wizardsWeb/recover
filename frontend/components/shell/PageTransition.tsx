"use client";

import { motion, useReducedMotion } from "framer-motion";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { PAGE_ENTER } from "@/lib/motion";

/**
 * The entrance every dashboard page gets.
 *
 * Keyed on the pathname, and that key is the whole point. Without it React
 * reconciles this `motion.div` across a navigation — same type, same position —
 * so `initial` never runs again and only the very first page of a session
 * animates. With it, each route mounts its own element and gets its own
 * entrance.
 *
 * 12px and 300ms, which is deliberately small. A page transition's job is to
 * say "this is new content", not to make the reader wait for it; anything
 * longer turns every navigation into a toll.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const prefersReducedMotion = useReducedMotion();

  if (prefersReducedMotion) return <>{children}</>;

  return (
    <motion.div key={pathname} {...PAGE_ENTER}>
      {children}
    </motion.div>
  );
}
