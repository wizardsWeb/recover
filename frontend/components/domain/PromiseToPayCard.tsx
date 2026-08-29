"use client";

import { CalendarClock } from "lucide-react";

/**
 * A promise the customer made, and how long is left on it.
 *
 * This is the state the agent is worst at representing without help: the
 * customer has not paid and has not refused. The case is open, quiet, and
 * *deliberately* quiet — and without this card a merchant looking at it sees a
 * stalled recovery and reaches for the Escalate button.
 *
 * The date is shown as the customer wrote it ("25 tak", "next month") and only
 * resolved when that is unambiguous. Rendering "25 tak" as a confident calendar
 * date would be the UI asserting something the classifier explicitly declined to
 * assert — the extraction copies the customer's words precisely so this layer
 * cannot invent a deadline nobody agreed to.
 */

interface Promise {
  date_hint?: string | null;
  partial_pct?: number | null;
  amount_mentioned?: number | null;
  reason_offered?: string | null;
  promised_at?: string | null;
  raw_reply?: string | null;
}

/**
 * Resolve a day-of-month hint to a date, when it is safe to.
 *
 * Handles the one form that is unambiguous: a bare day number ("25 tak", "the
 * 20th") means the next occurrence of that day. Everything else — "next month",
 * "kal", a weekday — returns null and is shown verbatim.
 */
function resolveDueDate(hint: string | null | undefined): Date | null {
  if (!hint) return null;
  const day = /^(\d{1,2})\b/.exec(hint.trim());
  if (!day) return null;

  const dayOfMonth = Number(day[1]);
  if (dayOfMonth < 1 || dayOfMonth > 31) return null;

  const now = new Date();
  const candidate = new Date(now.getFullYear(), now.getMonth(), dayOfMonth);
  if (candidate < now) candidate.setMonth(candidate.getMonth() + 1);
  return candidate;
}

function daysUntil(date: Date): number {
  const ms = date.getTime() - Date.now();
  return Math.ceil(ms / (1000 * 60 * 60 * 24));
}

export function PromiseToPayCard({ promise }: { promise: Promise }) {
  const due = resolveDueDate(promise.date_hint);
  const remaining = due ? daysUntil(due) : null;
  // Amber once the date has passed: the promise is not broken — the customer may
  // still pay — but it is no longer a reason to stay quiet.
  const overdue = remaining !== null && remaining < 0;

  return (
    <div
      className={`space-y-2 rounded-lg border border-l-4 p-3 ${
        overdue
          ? "border-warning/40 border-l-warning bg-warning-subtle"
          : "border-success/40 border-l-success bg-success-subtle"
      }`}
    >
      <div className="flex items-center gap-2">
        <CalendarClock size={14} className={overdue ? "text-warning" : "text-success"} />
        <span
          className={`text-sm font-medium ${overdue ? "text-warning" : "text-success"}`}
        >
          Promise to pay
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {promise.partial_pct != null ? (
          <span className="rounded-none bg-elevated px-2 py-0.5 font-mono text-[10px] text-ink">
            {promise.partial_pct}% now
          </span>
        ) : null}
        <span className="rounded-none bg-elevated px-2 py-0.5 text-[10px] text-ink">
          {remaining === null
            ? `Due ${promise.date_hint ?? "date not given"}`
            : overdue
              ? `${Math.abs(remaining)} days past the promised date`
              : remaining === 0
                ? "Promised for today"
                : `Promise due in ${remaining} day${remaining === 1 ? "" : "s"}`}
        </span>
        {promise.reason_offered ? (
          <span className="rounded-none bg-elevated px-2 py-0.5 text-[10px] text-ink-muted">
            {promise.reason_offered.replace(/_/g, " ")}
          </span>
        ) : null}
      </div>

      {promise.raw_reply ? (
        <blockquote
          className={`border-l-2 pl-2 text-xs text-ink-muted italic ${
            overdue ? "border-warning/40" : "border-success/40"
          }`}
        >
          “{promise.raw_reply}”
        </blockquote>
      ) : null}

      <p className="text-[10px] text-ink-faint">
        Recovery is paused until the promised date. The agent is not chasing this case.
      </p>
    </div>
  );
}
