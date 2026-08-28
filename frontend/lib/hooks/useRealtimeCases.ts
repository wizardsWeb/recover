"use client";

import { useEffect, useRef, useState } from "react";

import { createClient } from "@/lib/supabase/client";

export type RealtimeStatus = "connecting" | "live" | "offline";

/**
 * Subscribe to inserts and updates on `recovery_cases`.
 *
 * The callback is held in a ref rather than listed as an effect dependency. An
 * inline arrow passed by the caller is a new function on every render, so
 * depending on it directly would tear down and rebuild the websocket channel on
 * each render — which reads as a connection that flaps for no reason and drops
 * events in the gap.
 *
 * `onChange` deliberately carries no payload. Realtime delivers the raw
 * `recovery_cases` row; every screen here renders a *joined* shape (the
 * customer's name, the derived step). Handing callers a row that is missing the
 * fields they render invites reconstructing a half-populated case, so the hook
 * reports only that something moved and lets the caller re-read.
 *
 * Connection loss is state, not an error: `status` goes to `offline` and the
 * page keeps showing the data it already has. Supabase reconnects on its own.
 */
export function useRealtimeCases(onChange: () => void): RealtimeStatus {
  const [status, setStatus] = useState<RealtimeStatus>("connecting");
  const callbackRef = useRef(onChange);

  useEffect(() => {
    callbackRef.current = onChange;
  }, [onChange]);

  useEffect(() => {
    const supabase = createClient();
    const channel = supabase
      .channel("recovery-cases-stream")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "recovery_cases" },
        () => callbackRef.current(),
      )
      .subscribe((subscribeStatus) => {
        if (subscribeStatus === "SUBSCRIBED") {
          setStatus("live");
        } else if (subscribeStatus === "CHANNEL_ERROR" || subscribeStatus === "TIMED_OUT") {
          setStatus("offline");
        } else if (subscribeStatus === "CLOSED") {
          setStatus("offline");
        }
      });

    return () => {
      void supabase.removeChannel(channel);
    };
  }, []);

  return status;
}
