"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";

import { CodeBlock } from "@/components/ui/code-block";

/**
 * One step of the agent loop, collapsed by default.
 *
 * The summary line is what a merchant reads; the JSON underneath is what an
 * engineer or an auditor reads. Both are present because the same page has to
 * serve both, and hiding the raw detail entirely would make the trail something
 * you have to take on trust.
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

  return (
    <div className="overflow-hidden rounded-lg border border-hairline">
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-subtle"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span
          className={`font-mono text-xs font-medium tracking-wider uppercase ${STATUS_COLORS[status]}`}
        >
          {stepName}
        </span>
        {badge}
        <span className="ml-auto font-mono text-xs text-ink-faint">
          {IST_TIME.format(new Date(timestamp))}
        </span>
      </button>
      {expanded ? (
        <div className="space-y-3 bg-subtle px-4 pb-4">
          {children}
          {details ? <CodeBlock value={details} language="json" /> : null}
        </div>
      ) : null}
    </div>
  );
}
