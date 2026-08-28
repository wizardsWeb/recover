"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { createHandoff, overrideCase } from "@/lib/api/cases";

/**
 * Human overrides.
 *
 * Every one of these writes an `audit_events` row attributed to `human`, which
 * is the point: an agent that can be overridden without a record is an agent
 * nobody can be held accountable for — in either direction. The merchant taking
 * a case back is as much a part of the trail as the agent working it.
 *
 * Stop and Escalate ask for a reason and Pause does not, because the reason is
 * only load-bearing where someone will read it later. A stopped case is one a
 * colleague may query months on; an escalated one lands on a person's queue and
 * the reason is the first thing they see. Pausing is reversible and self-evident,
 * and demanding a sentence for it would train people to type "asdf".
 */

type Action = "pause" | "stop" | "escalate";

interface ActionSpec {
  action: Action;
  label: string;
  className: string;
  /** Shown in the dialog — what actually happens, not a restatement of the label. */
  consequence: string;
  needsReason: boolean;
}

const ACTIONS: ActionSpec[] = [
  {
    action: "pause",
    label: "Pause recovery",
    className: "text-ink-muted",
    consequence:
      "The agent stops working this case. Nothing further is sent, and the case can be reopened.",
    needsReason: false,
  },
  {
    action: "stop",
    label: "Stop & close",
    className: "text-danger",
    consequence:
      "The case closes for good. No further messages, retries, or follow-ups on this recovery.",
    needsReason: true,
  },
  {
    action: "escalate",
    label: "Escalate to human",
    className: "text-ink-muted",
    consequence:
      "A handoff card is created for your team with the customer's history and suggested next steps.",
    needsReason: true,
  },
];

export function CaseActions({
  caseId,
  status,
}: {
  caseId: string;
  status: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState<ActionSpec | null>(null);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<Action | null>(null);

  // A closed case has nothing left to pause, stop, or escalate. The buttons are
  // disabled rather than hidden so the page does not change shape when a case
  // closes underneath the reader.
  const isClosed = ["recovered", "stopped", "failed"].includes(status);
  const busy = pending !== null;

  async function confirm(spec: ActionSpec) {
    const note = reason.trim() || `${spec.label} from case detail`;
    setPending(spec.action);
    setOpen(null);

    try {
      await overrideCase(caseId, spec.action, note);

      // Escalation is two writes: the override moves the case, the handoff
      // gives the person picking it up something to act on. The briefing is
      // best-effort — a case that moved but has no card is recoverable; failing
      // the whole action after the status already changed is not.
      if (spec.action === "escalate") {
        try {
          await createHandoff(caseId, note);
        } catch {
          toast.warning("Case escalated, but the handoff card could not be created.");
        }
      }

      toast.success(`${spec.label} — recorded in the audit trail`);
      // The timeline is server-rendered, so the new rows only appear once the
      // route's data is refetched.
      router.refresh();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Override failed");
    } finally {
      setPending(null);
      setReason("");
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-ink-faint">
        {isClosed
          ? "This case is closed. Overrides are no longer available."
          : "Human overrides are logged to the audit trail."}
      </p>

      {ACTIONS.map((spec) => (
        <button
          key={spec.action}
          type="button"
          disabled={busy || isClosed}
          onClick={() => {
            setReason("");
            setOpen(spec);
          }}
          className={`flex w-full items-center gap-2 rounded border border-hairline px-3 py-2 text-left text-xs transition-colors hover:bg-subtle disabled:cursor-not-allowed disabled:opacity-50 ${spec.className}`}
        >
          {pending === spec.action ? (
            <Loader2 size={12} className="animate-spin" />
          ) : null}
          {spec.label}
        </button>
      ))}

      <AlertDialog open={open !== null} onOpenChange={(next) => !next && setOpen(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{open?.label}</AlertDialogTitle>
            <AlertDialogDescription>{open?.consequence}</AlertDialogDescription>
          </AlertDialogHeader>

          {open?.needsReason ? (
            <div className="space-y-1.5">
              <label htmlFor="override-reason" className="text-xs text-ink-muted">
                Reason
              </label>
              <Textarea
                id="override-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Why are you taking this case over?"
                rows={3}
                maxLength={1000}
              />
              <p className="text-[10px] text-ink-faint">
                Stored on the audit trail and shown to whoever picks the case up.
              </p>
            </div>
          ) : null}

          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => open && void confirm(open)}>
              {open?.label}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
