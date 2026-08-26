"use client";

import { ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { CodeBlock } from "@/components/ui/code-block";
import { cn } from "@/lib/utils/cn";
import { getSimulatorStatus, type EventType, type RecentEvent } from "@/lib/api/simulator";
import { Panel, useSimulatorRefresh } from "./SimulatorPanels";

const POLL_INTERVAL_MS = 2000;

/**
 * Colour by what the event *means*, not by type alphabetically: a failed
 * payment and a broken mandate are both money already lost, an abandoned cart
 * is money at risk, an overdue invoice is money that is merely late.
 */
const EVENT_STYLES: Record<EventType, string> = {
  "payment.failed": "bg-danger-subtle text-danger",
  "subscription.charged.failed": "bg-danger-subtle text-danger",
  "checkout.abandoned": "bg-warning-subtle text-warning",
  "invoice.overdue": "bg-info-subtle text-ink-blue",
  "customer.replied": "bg-brand-subtle text-brand",
};

/** "12 seconds ago" — coarse on purpose; this is a tail, not a stopwatch. */
function relativeTime(iso: string, now: number): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds} second${seconds === 1 ? "" : "s"} ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  return `${Math.round(hours / 24)} day${Math.round(hours / 24) === 1 ? "" : "s"} ago`;
}

export function EventLogTail() {
  const { token } = useSimulatorRefresh();
  const [events, setEvents] = useState<RecentEvent[]>([]);
  const [ready, setReady] = useState(false);
  // Re-rendered on a tick so the relative timestamps keep counting up even
  // when the poll returns an unchanged list.
  const [now, setNow] = useState(() => Date.now());
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const status = await getSimulatorStatus();
        if (cancelled) return;
        setEvents(status.recentEvents);
        setNow(Date.now());
      } catch {
        // A failed poll is not worth a toast every two seconds. The panel keeps
        // showing the last good list and the next tick will recover.
      } finally {
        if (!cancelled) setReady(true);
      }
    }

    void poll();
    const timer = window.setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [token]);

  // A firing elsewhere on the page puts a new event at the top; show it.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  }, [token]);

  return (
    <Panel
      title="Event stream"
      description="The last 20 events for this merchant"
      actions={
        <span className="flex items-center gap-1.5 text-xs text-ink-faint">
          <span className="relative flex size-1.5">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
            <span className="relative inline-flex size-1.5 rounded-full bg-success" />
          </span>
          Auto-refresh: on
        </span>
      }
    >
      <div
        ref={scrollRef}
        className="max-h-[26rem] overflow-y-auto rounded-md bg-inset p-2 dark:bg-subtle"
      >
        {events.length === 0 ? (
          <p className="px-2 py-10 text-center text-sm text-ink-faint">
            {ready ? "No events yet. Fire a scenario to see the stream." : "Connecting…"}
          </p>
        ) : (
          <ul className="space-y-1.5">
            {events.map((event) => (
              <li key={event.id} className="rounded-md bg-elevated px-3 py-2">
                <details className="group/event">
                  <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2">
                    <ChevronRight
                      className="size-3 shrink-0 text-ink-faint transition-transform group-open/event:rotate-90"
                      strokeWidth={2}
                      aria-hidden
                    />
                    <Badge className={cn("font-mono", EVENT_STYLES[event.eventType])}>
                      {event.eventType}
                    </Badge>
                    <span className="text-sm text-ink">{event.customerName ?? "—"}</span>
                    <span className="ml-auto font-mono text-xs text-ink-faint">
                      {relativeTime(event.receivedAt, now)}
                    </span>
                  </summary>
                  <CodeBlock value={event.payload} className="mt-2" />
                </details>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}
