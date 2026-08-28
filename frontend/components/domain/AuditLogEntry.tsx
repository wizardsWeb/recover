"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/ui/code-block";
import type { AuditEvent } from "@/lib/api/cases";

/**
 * One row of the audit trail.
 *
 * The actor badge is the first thing on the line after the time, because the
 * question the trail exists to answer is "who did this" — and `system` (a rule
 * fired) is a different answer from `agent` (a model chose) or `human` (someone
 * overrode it).
 */

const ACTOR_STYLES: Record<AuditEvent["actor"], string> = {
  agent: "bg-brand-subtle text-brand",
  human: "bg-success-subtle text-success",
  system: "bg-info-subtle text-info",
  customer: "bg-gold-light text-gold",
};

const IST_TIME = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

export function AuditLogEntry({ entry }: { entry: AuditEvent }) {
  const [expanded, setExpanded] = useState(false);
  const actorStyle = ACTOR_STYLES[entry.actor] ?? ACTOR_STYLES.system;
  // `guardrail:guardrail_block` reads as `guardrail → guardrail block`.
  const eventLabel = entry.event.replace(":", " → ").replace(/_/g, " ");

  return (
    <div>
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-subtle"
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown size={12} className="shrink-0" />
        ) : (
          <ChevronRight size={12} className="shrink-0" />
        )}
        <span className="w-24 shrink-0 font-mono text-xs text-ink-faint">
          {IST_TIME.format(new Date(entry.created_at))}
        </span>
        <Badge className={`shrink-0 text-xs ${actorStyle}`}>{entry.actor}</Badge>
        <span className="truncate text-sm text-ink-muted">{eventLabel}</span>
      </button>
      {expanded ? (
        <div className="bg-subtle px-10 pb-3">
          <CodeBlock value={entry.details ?? {}} language="json" />
        </div>
      ) : null}
    </div>
  );
}
