"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api/client";
import { getFixtureStatus, loadFixtures, resetFixtures, type FixtureStatus } from "@/lib/api/simulator";
import { Panel, useSimulatorRefresh } from "./SimulatorPanels";

/** Typing the word is the confirmation — a reset is not undoable. */
const RESET_PHRASE = "RESET";

export function FixturePanel() {
  const { token, refresh } = useSimulatorRefresh();
  const [status, setStatus] = useState<FixtureStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  // Fetching inside the effect rather than through a callback defined above
  // it: this is a subscription to an external system, and React's compiler
  // lint is right that a synchronous setState from an effect body is not.
  // `token` is the dependency that re-runs it when a sibling panel acts.
  useEffect(() => {
    let cancelled = false;

    async function read() {
      try {
        const next = await getFixtureStatus();
        if (!cancelled) setStatus(next);
      } catch (error) {
        if (!cancelled) {
          toast.error(error instanceof ApiError ? error.message : "Could not read fixture status");
        }
      }
    }

    void read();
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onLoad() {
    setBusy(true);
    try {
      const result = await loadFixtures();
      toast.success(result.message);
      refresh();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not load fixtures");
    } finally {
      setBusy(false);
    }
  }

  async function onReset() {
    setBusy(true);
    try {
      const result = await resetFixtures();
      const total = Object.values(result.deleted).reduce((sum, count) => sum + count, 0);
      toast.success(`${result.message} ${total} rows deleted.`);
      setConfirmOpen(false);
      setConfirmText("");
      refresh();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not reset fixtures");
    } finally {
      setBusy(false);
    }
  }

  const counts = status?.counts;

  return (
    <Panel
      id="simulator-fixtures"
      title="Fixtures"
      description="The six persona customers every scenario depends on"
      actions={
        busy ? <span className="text-xs text-ink-faint">Working…</span> : null
      }
    >
      <div className="space-y-4">
        <div className="rounded-md bg-subtle px-3 py-2.5">
          {status === null ? (
            <p className="text-sm text-ink-muted">Checking…</p>
          ) : status.loaded ? (
            <p className="text-sm text-ink">
              <span className="font-medium text-success">Loaded</span>
              {" — "}
              {counts?.customers} customers, {counts?.paymentMethods} payment methods,{" "}
              {counts?.cases} cases, {counts?.events} events
            </p>
          ) : (
            <p className="text-sm text-ink-muted">
              <span className="font-medium text-ink">Not loaded</span> — fire a scenario and it will
              be refused until the personas exist.
            </p>
          )}
        </div>

        {status && status.personas.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {status.personas.map((name) => (
              <Badge key={name} variant="secondary">
                {name.split(" ")[0]}
              </Badge>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          <Button onClick={onLoad} disabled={busy}>
            {status?.loaded ? "Reload demo fixtures" : "Load demo fixtures"}
          </Button>
          <Button variant="destructive" onClick={() => setConfirmOpen(true)} disabled={busy}>
            Reset all data
          </Button>
        </div>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reset all simulator data?</DialogTitle>
            <DialogDescription>
              This deletes all simulator-created customers, cases, events, and audit logs for your
              merchant. Customers you added yourself are left alone. Type{" "}
              <span className="font-mono font-medium text-ink">{RESET_PHRASE}</span> to confirm.
            </DialogDescription>
          </DialogHeader>
          <Input
            value={confirmText}
            onChange={(event) => setConfirmText(event.target.value)}
            placeholder={RESET_PHRASE}
            aria-label={`Type ${RESET_PHRASE} to confirm`}
            autoComplete="off"
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={onReset} disabled={busy || confirmText !== RESET_PHRASE}>
              {busy ? "Resetting…" : "Reset everything"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Panel>
  );
}
