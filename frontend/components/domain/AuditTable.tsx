"use client";

import Link from "next/link";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Bot, ChevronRight, MessageCircle, Settings, User } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Fragment, useId, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/ui/code-block";
import { StaggerItem, StaggerList } from "@/components/ui/StaggerList";
import { Table, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AuditEvent } from "@/lib/api/cases";
import { SPRING } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

/**
 * The actor, as an icon and a word.
 *
 * The question the trail exists to answer is "who did this", and the four
 * answers are genuinely different claims: `system` means a rule fired, `agent`
 * means a model chose, `human` means someone overrode it, `customer` means
 * someone replied. An icon makes the distinction survive a fast scan down a
 * hundred rows in a way four tints of the same badge does not.
 */
const ACTORS: Record<AuditEvent["actor"], { className: string; icon: LucideIcon }> = {
  agent: { className: "bg-brand-subtle text-brand", icon: Bot },
  human: { className: "bg-success-subtle text-success", icon: User },
  system: { className: "bg-info-subtle text-info", icon: Settings },
  customer: { className: "bg-gold-light text-gold", icon: MessageCircle },
};

const IST_TIME = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const COLUMNS = ["", "Time", "Actor", "Event", "Case"];

export function AuditTable({ events }: { events: readonly AuditEvent[] }) {
  return (
    <div className="overflow-x-auto rounded-none border border-hairline bg-elevated shadow-card">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {COLUMNS.map((label, index) => (
              <TableHead
                key={label || index}
                className="h-9 px-3 text-[11px] font-medium tracking-[0.06em] text-ink-faint uppercase"
              >
                {label}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>

        <StaggerList as="tbody" stagger={0.02}>
          {events.map((entry) => (
            <AuditRow key={entry.id} entry={entry} />
          ))}
        </StaggerList>
      </Table>
    </div>
  );
}

/**
 * One row, plus the payload row underneath it.
 *
 * Two `<tr>`s rather than one row with an absolutely-positioned drawer: a table
 * cell cannot contain a second row, and faking the structure with divs would
 * cost the column alignment that makes a hundred rows scannable in the first
 * place.
 *
 * The event string is split at the colon and the two halves are coloured
 * differently. `guardrail:guardrail_block` is a step and an outcome, and a
 * reader scanning for "what happened in the decide step" is scanning the left
 * half — giving it the brand colour turns the column into two columns for free.
 */
function AuditRow({ entry }: { entry: AuditEvent }) {
  const [expanded, setExpanded] = useState(false);
  const prefersReducedMotion = useReducedMotion();
  const detailId = useId();

  const actor = ACTORS[entry.actor] ?? ACTORS.system;
  const ActorIcon = actor.icon;
  const [step, outcome] = entry.event.includes(":")
    ? entry.event.split(":", 2)
    : [entry.event, ""];
  const humanise = (value: string) => value.replace(/_/g, " ");

  return (
    <Fragment>
      <StaggerItem as="tr" className="border-b border-hairline hover:bg-brand-subtle">
        <TableCell className="w-8 px-3 py-2">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
            aria-controls={detailId}
            aria-label={expanded ? "Hide payload" : "Show payload"}
            className="flex rounded-md p-0.5 text-ink-faint transition-colors hover:text-ink"
          >
            <motion.span
              aria-hidden
              animate={{ rotate: expanded ? 90 : 0 }}
              transition={prefersReducedMotion ? { duration: 0 } : SPRING}
              className="flex"
            >
              <ChevronRight className="size-3.5" strokeWidth={2} />
            </motion.span>
          </button>
        </TableCell>

        <TableCell className="px-3 py-2 font-mono text-[13px] text-ink-muted tabular-nums">
          {IST_TIME.format(new Date(entry.created_at))}
        </TableCell>

        <TableCell className="px-3 py-2">
          <Badge className={cn("shrink-0", actor.className)}>
            <ActorIcon aria-hidden />
            {entry.actor}
          </Badge>
        </TableCell>

        <TableCell className="px-3 py-2 text-sm">
          <span className="font-medium text-brand">{humanise(step)}</span>
          {outcome ? (
            <>
              <span aria-hidden className="mx-1.5 text-ink-faint">
                →
              </span>
              <span className="text-ink">{humanise(outcome)}</span>
            </>
          ) : null}
        </TableCell>

        <TableCell className="px-3 py-2">
          {entry.case_id ? (
            <Link
              href={`/app/cases/${entry.case_id}`}
              className="font-mono text-[11px] text-ink-faint transition-colors hover:text-brand"
            >
              {entry.case_id.slice(0, 8)}
            </Link>
          ) : (
            <span className="font-mono text-[11px] text-ink-faint">—</span>
          )}
        </TableCell>
      </StaggerItem>

      <tr id={detailId} className={cn(!expanded && "hidden")}>
        <td colSpan={COLUMNS.length} className="p-0">
          <AnimatePresence initial={false}>
            {expanded ? (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={
                  prefersReducedMotion ? { duration: 0 } : { duration: 0.2, ease: "easeOut" }
                }
                className="overflow-hidden border-b border-hairline bg-subtle"
              >
                <div className="px-11 py-3">
                  <CodeBlock value={entry.details ?? {}} language="json" />
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </td>
      </tr>
    </Fragment>
  );
}
