"use client";

import { Users } from "lucide-react";

import { formatINR } from "@/lib/utils/format";

/**
 * The briefing a person picking this case up cold actually needs.
 *
 * A handoff is not a failure state and this is not a log line. scenarios.md S5
 * makes the point plainly: the agent's contribution there is ₹0 recovered and a
 * ₹36,000 customer kept, and the customer is kept because whoever calls arrives
 * knowing the tenure, the value, and the customer's own words.
 *
 * Amber rather than red. Red is for the opt-out card, where something is
 * forbidden; this is a case in a queue, waiting on a person — a different state
 * and a different colour, or neither means anything.
 *
 * Everything rendered here was assembled deterministically from case data by
 * `app/agent/handoff.py`. No model wrote any of it, which is why a tenure or a
 * suggested action can be read at face value.
 */

const REASON_LABELS: Record<string, string> = {
  churn: "Customer confirmed churn",
  hardship: "Customer signalled hardship",
  human_escalation: "Escalated by a human operator",
};

const ACTION_LABELS: Record<string, string> = {
  offer_3_month_pause: "Offer a 3-month pause",
  downgrade_to_cheaper_tier: "Downgrade to a cheaper tier",
  schedule_retention_call: "Schedule a retention call",
  offer_payment_plan: "Offer a payment plan",
  pause_subscription_60_days: "Pause the subscription for 60 days",
  waive_current_month: "Waive the current month",
  review_case_history: "Review the case history",
  contact_customer_directly: "Contact the customer directly",
  adjust_playbook_settings: "Adjust the playbook settings",
};

interface HandoffPayload {
  reason?: string;
  reason_label?: string;
  note?: string | null;
  customer?: {
    name?: string | null;
    ltv_cents?: number;
    tenure_days?: number;
  };
  chosen_arm?: string | null;
  customer_reply?: string | null;
  suggested_retention_actions?: string[];
}

export function HumanHandoffCard({ payload }: { payload: HandoffPayload }) {
  const customer = payload.customer ?? {};
  const reason = payload.reason ?? "human_escalation";
  const actions = payload.suggested_retention_actions ?? [];

  return (
    <div className="space-y-3 rounded-lg border border-warning/40 border-l-4 border-l-warning bg-warning-subtle p-3">
      <div className="flex items-center gap-2">
        <Users size={14} className="text-warning" />
        <span className="text-sm font-medium text-warning">Handed off to human team</span>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded-4xl bg-elevated px-2 py-0.5 text-[10px] font-medium text-ink">
          {payload.reason_label ?? REASON_LABELS[reason] ?? reason}
        </span>
        {customer.ltv_cents ? (
          <span className="rounded-4xl bg-elevated px-2 py-0.5 font-mono text-[10px] text-ink">
            LTV {formatINR(customer.ltv_cents)}
          </span>
        ) : null}
        {customer.tenure_days ? (
          <span className="rounded-4xl bg-elevated px-2 py-0.5 font-mono text-[10px] text-ink-muted">
            {customer.tenure_days} days
          </span>
        ) : null}
      </div>

      {payload.customer_reply ? (
        <blockquote className="border-l-2 border-warning/40 pl-2 text-xs text-ink-muted italic">
          “{payload.customer_reply}”
        </blockquote>
      ) : null}

      {payload.note ? <p className="text-xs text-ink-muted">{payload.note}</p> : null}

      {actions.length > 0 ? (
        <div className="space-y-1">
          <div className="text-[10px] tracking-wide text-ink-faint uppercase">
            Suggested next steps
          </div>
          <ul className="space-y-0.5">
            {actions.map((action) => (
              <li key={action} className="flex gap-2 text-xs text-ink">
                <span className="text-warning">•</span>
                <span>{ACTION_LABELS[action] ?? action.replace(/_/g, " ")}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="border-t border-warning/20 pt-2 text-[10px] text-ink-faint">
        This case is no longer being processed by the agent.
      </p>
    </div>
  );
}
