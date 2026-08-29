"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

import { SPRING } from "@/lib/motion";

/**
 * The header's entrance, split out so `Header` itself can stay on the server.
 *
 * Only the `<header>` element needs to be a client component to animate; the
 * breadcrumb, the palette trigger and the user menu are passed in as children
 * and are rendered by the server exactly as before. Making `Header` a client
 * component instead would pull its whole subtree — and `isProduction` with it —
 * into the browser bundle to win one drop-in.
 *
 * It drops in from `y: -20` rather than fading: the bar is chrome arriving
 * above the content, and a fade reads as the page still loading.
 */
export function HeaderShell({ children }: { children: ReactNode }) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <motion.header
      initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: -20 }}
      animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
      transition={prefersReducedMotion ? { duration: 0 } : SPRING}
      className="flex h-[52px] shrink-0 items-center gap-4 border-b border-hairline bg-base px-6 print:hidden"
    >
      {children}
    </motion.header>
  );
}
