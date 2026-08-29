"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { ChevronRight } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";

import { CodeBlock } from "@/components/ui/code-block";
import { SPRING } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

/**
 * One step of the agent loop, collapsed by default.
 *
 * The summary line is what a merchant reads; the JSON underneath is what an
 * engineer or an auditor reads. Both are present because the same page has to
 * serve both, and hiding the raw detail entirely would make the trail something
 * you have to take on trust.
 *
 * The expansion animates `height: auto` through `AnimatePresence`, which is the
 * one case where animating a layout property is worth the cost: the panel's
 * height is not knowable in advance — it depends on how much JSON the step
 * produced — so the alternatives are a hard-coded max-height that clips long
 * payloads, or a snap that makes the page jump under the reader's cursor.
 *
 * One chevron that rotates rather than two icons that swap. A swap is a new
 * element every toggle and cannot animate between the two states.
 */

export type StepStatus = "success" | "blocked" | "skipped" | "pending";

const STATUS_COLORS: Record<StepStatus, string> = {
  success: "text-success",
  blocked: "text-danger",
  skipped: "text-ink-faint",
  pending: "text-warning",
};

/** Times render in IST — the merchants, the customers and the rules are all Indian. */
const IST_TIME = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

export function StepResultCard({
  stepName,
  status,
  timestamp,
  details,
  badge,
  children,
}: {
  stepName: string;
  status: StepStatus;
  timestamp: string;
  details?: Record<string, unknown>;
  /** Rendered in the collapsed header, so provenance is visible without a click. */
  badge?: ReactNode;
  children?: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const prefersReducedMotion = useReducedMotion();

  return (
    <div className="overflow-hidden rounded-none border border-hairline bg-elevated shadow-card">
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-150 hover:bg-subtle"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        <motion.span
          aria-hidden
          animate={{ rotate: expanded ? 90 : 0 }}
          transition={prefersReducedMotion ? { duration: 0 } : SPRING}
          className="flex shrink-0 text-ink-faint"
        >
          <ChevronRight className="size-3.5" strokeWidth={2} />
        </motion.span>
        <span
          className={cn(
            "font-mono text-xs font-medium tracking-[0.06em] uppercase",
            STATUS_COLORS[status],
          )}
        >
          {stepName}
        </span>
        {badge}
        <span className="ml-auto font-mono text-xs text-ink-faint">
          {IST_TIME.format(new Date(timestamp))}
        </span>
      </button>

      <AnimatePresence initial={false}>
        {expanded ? (
          <motion.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={
              prefersReducedMotion ? { duration: 0 } : { duration: 0.25, ease: "easeOut" }
            }
            // The wrapper clips while the height animates; the padding lives on
            // the inner element so it is not part of what is being animated —
            // padding on a collapsing box makes the content jump at the end.
            className="overflow-hidden border-t border-hairline bg-subtle"
          >
            <div className="space-y-3 px-4 py-4">
              {children}
              {details ? <CodeBlock value={details} language="json" /> : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
