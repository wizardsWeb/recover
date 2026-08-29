"use client";

/**
 * What the network is doing right now.
 *
 * The banner is the only part of this page that has to be live. A heatmap that
 * is a minute stale is fine; an outage banner that is a minute stale is a
 * merchant watching retries fail while the page says all is well.
 *
 * **The socket is a notification, not a source of truth.** Every event triggers
 * a re-read of `/api/network/alerts` rather than mutating local state from the
 * payload. Applying the payload directly would be faster and would drift: a
 * missed message while the tab was backgrounded leaves the banner permanently
 * wrong, with nothing to correct it. Re-reading means the worst case of a
 * dropped message is one late render, not a wrong one.
 *
 * A failed connection degrades to the server-rendered alerts with the live dot
 * off. The alternative — hiding the banner because the socket is down — would
 * hide an outage during exactly the kind of network trouble that causes one.
 */

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { AlertTriangle, CheckCircle2, RadioTower } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import type { AlertsResponse, NetworkAlert, StreamEvent } from "@/lib/api/network";
import { alertStreamUrl, fetchAlerts } from "@/lib/api/network";
import { formatPercent, formatRelativeTime } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

type ConnectionState = "connecting" | "live" | "offline";

/**
 * Colour and copy per severity.
 *
 * `variant="destructive"` on shadcn's `Alert` only recolours the text, which is
 * right for a form error and not enough for an outage banner — so the fill and
 * the border come from the semantic tokens on top of it. Amber for degraded,
 * red for critical: a degraded instrument is still worth retrying into and a
 * critical one is not, and painting both red would flatten that decision.
 */
const SEVERITY: Record<string, { tone: string; label: string; destructive: boolean }> = {
  critical: {
    tone: "border-danger/40 bg-danger-subtle text-danger",
    label: "Critical",
    destructive: true,
  },
  high: {
    tone: "border-danger/30 bg-danger-subtle text-danger",
    label: "High",
    destructive: true,
  },
  medium: {
    tone: "border-warning/40 bg-warning-subtle text-warning",
    label: "Degraded",
    destructive: false,
  },
  low: {
    tone: "border-warning/30 bg-warning-subtle text-warning",
    label: "Minor",
    destructive: false,
  },
};

/** Backoff between reconnects, in ms. Capped so a long outage keeps retrying. */
const RECONNECT_MS = 5000;

function LiveDot({ state }: { state: ConnectionState }) {
  const tone =
    state === "live" ? "bg-success" : state === "connecting" ? "bg-warning" : "bg-ink-faint";
  const label =
    state === "live"
      ? "Live"
      : state === "connecting"
        ? "Connecting"
        : "Offline — showing the last reading";

  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-faint" title={label}>
      <span className={cn("size-1.5 rounded-full", tone)} aria-hidden />
      {label}
    </span>
  );
}

function AlertCard({ alert }: { alert: NetworkAlert }) {
  const severity = SEVERITY[alert.severity] ?? SEVERITY.medium;
  const instrument = [alert.bank, alert.method?.toUpperCase()].filter(Boolean).join(" ");

  return (
    <Alert
      variant={severity.destructive ? "destructive" : "default"}
      className={cn("rounded-card", severity.tone)}
    >
      {/* Never colour alone — the icon and the severity word carry the same
          meaning for anyone who cannot separate the two backgrounds. */}
      <AlertTriangle aria-hidden />
      <AlertTitle>
        {instrument || "Unknown instrument"} — {severity.label.toLowerCase()} degradation
      </AlertTitle>
      <AlertDescription className="text-current">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
          <p className="text-xs opacity-90">
            Detected {formatRelativeTime(alert.detected_at)}
            {alert.affected_merchants_count
              ? ` · affecting ${alert.affected_merchants_count} merchants on the network`
              : null}
          </p>

          <dl className="flex shrink-0 gap-4 font-mono text-xs tabular-nums">
            {alert.network_wide_success_rate !== null ? (
              <div>
                <dt className="text-[10px] tracking-[0.06em] uppercase opacity-70">Now</dt>
                <dd>{formatPercent(alert.network_wide_success_rate)}</dd>
              </div>
            ) : null}
            {alert.baseline_rate !== null ? (
              <div>
                <dt className="text-[10px] tracking-[0.06em] uppercase opacity-70">Normal</dt>
                <dd>{formatPercent(alert.baseline_rate)}</dd>
              </div>
            ) : null}
          </dl>
        </div>

        <p className="mt-3 border-t border-current/15 pt-2.5 text-xs opacity-90">
          Retries into this instrument are paused. The agent is falling back to the other channels
          its playbook allows.
        </p>
      </AlertDescription>
    </Alert>
  );
}

export function NetworkAlertBanner({ initial }: { initial: AlertsResponse }) {
  const [alerts, setAlerts] = useState<AlertsResponse>(initial);
  const [state, setState] = useState<ConnectionState>("connecting");
  const prefersReducedMotion = useReducedMotion();

  // Empty deps, so the identity is stable for the life of the component. That
  // is what lets the socket effect depend on it without tearing down and
  // rebuilding the connection on every render.
  const reconcile = useCallback(async () => {
    try {
      setAlerts(await fetchAlerts());
    } catch {
      // A failed re-read keeps the last known reading. Blanking the banner on a
      // transient error would hide an outage that is still happening.
    }
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    async function connect() {
      const url = await alertStreamUrl();
      if (!url || closed) {
        setState("offline");
        return;
      }

      socket = new WebSocket(url);

      socket.onopen = () => setState("live");
      socket.onmessage = (event) => {
        let payload: StreamEvent;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }
        // A heartbeat means the connection is healthy and nothing happened —
        // re-reading on one would poll the API every 30 seconds for no reason.
        if (payload.type === "alert_fired" || payload.type === "alert_resolved") {
          void reconcile();
        }
      };
      socket.onerror = () => setState("offline");
      socket.onclose = () => {
        setState("offline");
        if (!closed) retry = setTimeout(() => void connect(), RECONNECT_MS);
      };
    }

    void connect();

    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      // `onclose` is cleared first: without it the teardown's own close would
      // schedule a reconnect for a component that no longer exists.
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
    };
  }, [reconcile]);

  const active = alerts.active;
  const motionProps = prefersReducedMotion
    ? {}
    : {
        initial: { opacity: 0, y: -12, height: 0 },
        animate: { opacity: 1, y: 0, height: "auto" },
        exit: { opacity: 0, y: -12, height: 0 },
        transition: { duration: 0.25, ease: "easeOut" as const },
      };

  return (
    <section aria-live="polite" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold tracking-[-0.01em] text-ink">
          <RadioTower className="size-4 text-ink-faint" strokeWidth={1.75} aria-hidden />
          Network health
        </h2>
        <LiveDot state={state} />
      </div>

      <AnimatePresence initial={false} mode="popLayout">
        {active.length === 0 ? (
          <motion.div key="healthy" {...motionProps}>
            <Alert className="rounded-card border-success/30 bg-success-subtle text-success">
              <CheckCircle2 aria-hidden />
              <AlertTitle>All banks healthy</AlertTitle>
              <AlertDescription className="text-xs text-current opacity-90">
                Last checked {formatRelativeTime(alerts.checked_at)}
                {alerts.recent.length > 0
                  ? ` · ${alerts.recent.length} alert${alerts.recent.length === 1 ? "" : "s"} resolved in the last 24 hours`
                  : null}
              </AlertDescription>
            </Alert>
          </motion.div>
        ) : (
          active.map((alert) => (
            <motion.div key={alert.id} {...motionProps}>
              <AlertCard alert={alert} />
            </motion.div>
          ))
        )}
      </AnimatePresence>
    </section>
  );
}
