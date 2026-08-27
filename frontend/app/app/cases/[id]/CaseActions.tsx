"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/lib/api/client";
import { overrideCase } from "@/lib/api/cases";

/**
 * Human overrides.
 *
 * Every one of these writes an `audit_events` row attributed to `human`, which
 * is the point: an agent that can be overridden without a record is an agent
 * nobody can be held accountable for — in either direction. The merchant taking
 * a case back is as much a part of the trail as the agent working it.
 */

const ACTIONS = [
  { action: "pause", label: "Pause recovery", className: "text-ink-muted" },
  { action: "stop", label: "Stop & close", className: "text-danger" },
  { action: "escalate", label: "Escalate to human", className: "text-ink-muted" },
] as const;

export function CaseActions({ caseId }: { caseId: string }) {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);

  async function run(action: (typeof ACTIONS)[number]["action"], label: string) {
    setPending(action);
    try {
      await overrideCase(caseId, action, `${label} from case detail`);
      toast.success(`${label} — recorded in the audit trail`);
      // The timeline is server-rendered, so the new audit row only appears once
      // the route's data is refetched.
      router.refresh();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Override failed");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-xs text-ink-faint">Human overrides are logged to the audit trail.</p>
      {ACTIONS.map(({ action, label, className }) => (
        <button
          key={action}
          type="button"
          disabled={pending !== null}
          onClick={() => void run(action, label)}
          className={`w-full rounded border border-hairline px-3 py-2 text-left text-xs transition-colors hover:bg-subtle disabled:opacity-50 ${className}`}
        >
          {pending === action ? "Working…" : label}
        </button>
      ))}
    </div>
  );
}
