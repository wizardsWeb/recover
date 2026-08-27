"use client";

import {
  BookOpen,
  Cpu,
  Ear,
  FileCheck,
  GitBranch,
  Search,
  Shield,
  TrendingUp,
  Zap,
} from "lucide-react";
import type { ReactNode } from "react";

import { StepResultCard, type StepStatus } from "@/components/domain/StepResultCard";
import type { AuditEvent, CaseDetail } from "@/lib/api/cases";

/**
 * The agent's reasoning, in the order it happened.
 *
 * Built from `audit_events` rather than from the case row, because the trail is
 * the record of what the agent *did*, and the case row is only where it ended
 * up. A case that stopped at the guardrail shows five steps and no execute —
 * which is the truthful picture, and the one a merchant asking "why didn't you
 * send anything?" needs to see.
 *
 * Steps render in loop order, not arrival order. Two events from the same step
 * (a DOWNGRADE followed by its re-check) collapse into one entry showing the
 * final outcome, with every event still available in the expanded detail.
 */

const STEP_ICONS: Record<string, ReactNode> = {
  detect: <Search size={14} />,
  diagnose: <GitBranch size={14} />,
  uplift_check: <TrendingUp size={14} />,
  decide: <Cpu size={14} />,
  guardrail: <Shield size={14} />,
  execute: <Zap size={14} />,
  listen: <Ear size={14} />,
  learn: <BookOpen size={14} />,
  audit: <FileCheck size={14} />,
};

const STEP_ORDER = [
  "detect",
  "diagnose",
  "uplift_check",
  "decide",
  "guardrail",
  "execute",
  "listen",
  "learn",
  "audit",
];

const RAIL_STYLES: Record<StepStatus, string> = {
  success: "bg-success-subtle text-success",
  blocked: "bg-danger-subtle text-danger",
  skipped: "bg-subtle text-ink-faint",
  pending: "bg-warning-subtle text-warning",
};

interface GuardrailCheck {
  check_name: string;
  passed: boolean;
  reason?: string | null;
}

function stepStatus(event: AuditEvent): StepStatus {
  if (event.event.includes("block") || event.event.includes("stopped")) return "blocked";
  if (event.event.includes("skip")) return "skipped";
  return "success";
}

export function CaseTimeline({ caseDetail }: { caseDetail: CaseDetail }) {
  const byStep = new Map<string, AuditEvent[]>();
  for (const event of caseDetail.audit_events) {
    const step = event.event.split(":")[0];
    byStep.set(step, [...(byStep.get(step) ?? []), event]);
  }

  const stepsToShow = STEP_ORDER.filter((step) => byStep.has(step));

  if (stepsToShow.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-ink-faint">
        No agent steps recorded yet. The agent may still be processing.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {stepsToShow.map((stepName, index) => {
        const events = byStep.get(stepName) ?? [];
        // The last event is the step's outcome: a downgrade that then passed is
        // a pass, and showing the downgrade as the verdict would be wrong.
        const outcome = events[events.length - 1];
        const status = stepStatus(outcome);
        const checks = outcome.details?.checks as GuardrailCheck[] | undefined;
        const isLast = index === stepsToShow.length - 1;

        return (
          <div key={stepName} className="flex gap-3">
            <div className="flex flex-col items-center">
              <div
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${RAIL_STYLES[status]}`}
              >
                {STEP_ICONS[stepName]}
              </div>
              {!isLast ? <div className="my-1 w-px flex-1 bg-hairline" /> : null}
            </div>

            <div className="flex-1 pb-2">
              <StepResultCard
                stepName={stepName.replace(/_/g, " ")}
                status={status}
                timestamp={outcome.created_at}
                details={outcome.details}
              >
                {stepName === "guardrail" && checks ? (
                  <div className="space-y-1">
                    {checks.map((check) => (
                      <div key={check.check_name} className="flex items-start gap-2 text-xs">
                        <span className={check.passed ? "text-success" : "text-danger"}>
                          {check.passed ? "✓" : "✗"}
                        </span>
                        <span className="font-mono text-ink-muted">{check.check_name}</span>
                        {check.reason ? (
                          <span className="text-ink-faint">— {check.reason}</span>
                        ) : null}
                      </div>
                    ))}
                  </div>
                ) : null}

                {stepName === "listen" && outcome.details?.intent ? (
                  <div className="space-y-1 text-xs">
                    <div>
                      <span className="text-ink-faint">Intent: </span>
                      <span className="font-mono text-brand">{String(outcome.details.intent)}</span>
                    </div>
                    {outcome.details.opt_out_signal ? (
                      <div className="font-medium text-danger">
                        ⛔ Opt-out signal detected — consent revoked
                      </div>
                    ) : null}
                    {outcome.details.hardship_signal ? (
                      <div className="font-medium text-warning">
                        ⚠️ Hardship signal — human handoff triggered
                      </div>
                    ) : null}
                  </div>
                ) : null}

                {events.length > 1 ? (
                  <p className="text-xs text-ink-faint">
                    {events.length} events recorded for this step.
                  </p>
                ) : null}
              </StepResultCard>
            </div>
          </div>
        );
      })}
    </div>
  );
}
