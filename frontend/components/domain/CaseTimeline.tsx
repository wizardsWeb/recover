"use client";

import {
  BookOpen,
  Cpu,
  Ear,
  FileCheck,
  GitBranch,
  Search,
  Shield,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import type { ReactNode } from "react";

import { BanditAlternativesFan } from "@/components/domain/BanditAlternativesFan";
import { StepResultCard, type StepStatus } from "@/components/domain/StepResultCard";
import type {
  AgentDecision,
  AuditEvent,
  CaseDetail,
  CustomerReply,
  ExecutionAttempt,
} from "@/lib/api/cases";

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
 *
 * **The three LLM steps read past the audit row.** `audit_events.details` is
 * deliberately a summary — `diagnosis_complete` carries the root cause and the
 * posterior, not the evidence list; `execution_attempted` carries the adapter,
 * not the message body. The full payloads live on the rows that own them, so
 * the diagnose card reads `caseDetail.diagnosis`, the execute card reads the
 * matching `execution_attempts` row, and the listen card reads
 * `customer_replies`. Widening the audit rows to feed the UI would make an
 * append-only compliance trail grow with every presentation change.
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

/**
 * Enum values from `app/agent/prompts/diagnose_prompt.py`, plus the legacy stub
 * causes, rendered for a merchant rather than for a developer.
 *
 * Kept as an explicit map, not a prettified `replace(/_/g, " ")`: "b2b overdue
 * chronic late payment pattern" is not English, and the label is the sentence a
 * merchant reads when they ask why their money is late.
 */
const ROOT_CAUSE_LABELS: Record<string, string> = {
  salary_cycle_mismatch_with_competing_emi: "Salary arrives after the charge date",
  salary_cycle_mismatch: "Salary arrives after the charge date",
  insufficient_funds_transient: "Temporarily short of funds",
  insufficient_funds: "Temporarily short of funds",
  issuer_transient_failure: "Bank declined it temporarily",
  bank_downtime: "Bank outage at the time of charge",
  network_wide_psp_degradation: "Payment network degraded across merchants",
  mandate_revoked_or_expired: "Auto-pay mandate revoked or expired",
  mandate_revoked: "Auto-pay mandate revoked",
  mandate_not_registered: "Auto-pay mandate never registered",
  card_expired: "Card has expired",
  account_closed: "Bank account closed",
  price_sensitivity_at_checkout: "Hesitated at the price",
  distracted_multitasking: "Distracted mid-checkout",
  comparing_across_apps: "Comparing prices elsewhere",
  trust_hesitation_new_merchant: "Unsure about a first-time purchase",
  payment_method_unavailable_at_checkout: "Preferred payment method unavailable",
  chronic_late_payment_pattern: "Habitually pays late, but always pays",
  invoice_dispute: "Disputes the invoice",
  customer_churn_intent: "Intends to leave",
  technical_issue_unlogged: "Technical failure with no error logged",
  unknown: "Not established",
};

/** Human labels for the reply intents in `app/agent/models.py`. */
const INTENT_LABELS: Record<string, string> = {
  explicit_opt_out: "Asked us to stop",
  promise_to_pay: "Promised to pay",
  churn_confirmation: "Confirmed they're leaving",
  hardship_signal: "Signalled hardship",
  soft_promise: "Vague intent to pay",
  product_issue: "Reported a product issue",
  neutral: "Neutral",
  unknown: "Unclassified",
};

/** Entity keys from the listen schema, in the order they read best. */
const ENTITY_LABELS: Record<string, string> = {
  partial_pct: "Offered now",
  promise_date_hint: "By",
  amount_mentioned: "Amount named",
  reason_offered: "Reason",
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

function humanise(value: string): string {
  const spaced = value.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function rootCauseLabel(cause: string): string {
  return ROOT_CAUSE_LABELS[cause] ?? humanise(cause);
}

/**
 * Provenance, in the collapsed header.
 *
 * `is_stub` is a real field on every step result, precisely so the UI never has
 * to infer whether a model reasoned about a case. Showing it is the honest
 * counterpart to showing the conclusion.
 */
function ProvenanceBadge({ isStub }: { isStub: boolean }) {
  if (isStub) {
    return (
      <span className="rounded-4xl bg-warning-subtle px-2 py-0.5 text-[10px] font-medium text-warning">
        Stub
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-4xl bg-brand-subtle px-2 py-0.5 text-[10px] font-medium text-brand">
      <Sparkles size={9} />
      AI-diagnosed
    </span>
  );
}

/**
 * Rebuild the context bucket the bandit stored its posteriors under.
 *
 * Mirrors `make_context_bucket` in `app/agent/bandit/context.py`. Reconstructed
 * here rather than sent as its own column because the vector is the durable
 * record and the bucket is a pure function of four of its fields — storing both
 * would let them disagree.
 */
function buildContextBucket(vector: Record<string, unknown> | null): string | null {
  if (!vector) return null;
  const part = (key: string, fallback: string) => String(vector[key] ?? fallback);
  return [
    part("bank", "OTHE"),
    part("method", "OTH"),
    part("period", "unknown"),
    part("ltv_bucket", "low"),
  ].join(":");
}

/**
 * Who chose the action, in the collapsed header.
 *
 * A rule fallback and a bandit draw are different claims about how much the
 * agent knows, and the analytics compare them directly — so the timeline says
 * which one happened rather than leaving it to the expanded JSON.
 */
function DecideBadge({
  decision,
  contextBucket,
}: {
  decision: AgentDecision;
  contextBucket: string | null;
}) {
  const isBandit = decision.decision_source === "bandit";
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      {isBandit ? (
        <span
          className={`rounded-4xl px-2 py-0.5 text-[10px] font-medium ${
            decision.bandit_mode === "explore"
              ? "bg-info-subtle text-info"
              : "bg-brand-subtle text-brand"
          }`}
        >
          {decision.bandit_mode === "explore" ? "Explore" : "Exploit"}
        </span>
      ) : (
        <span className="rounded-4xl bg-warning-subtle px-2 py-0.5 text-[10px] font-medium text-warning">
          Rule fallback
        </span>
      )}
      {contextBucket ? (
        <span className="hidden truncate font-mono text-[10px] text-ink-faint sm:inline">
          {contextBucket}
        </span>
      ) : null}
    </span>
  );
}

/** A thin bar whose width *is* the posterior — the number and the picture agree. */
function ConfidenceBar({ probability }: { probability: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, probability)) * 100);
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-ink-faint">Confidence</span>
        <span className="font-mono text-ink-muted">{pct}%</span>
      </div>
      <div
        className="h-1 w-full overflow-hidden rounded-4xl bg-subtle"
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Diagnosis confidence"
      >
        <div className="h-full rounded-4xl bg-brand" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function DiagnoseDetail({ diagnosis }: { diagnosis: Record<string, unknown> }) {
  const rootCause = String(diagnosis.root_cause ?? "unknown");
  const probability = Number(diagnosis.posterior_probability ?? 0);
  const evidence = Array.isArray(diagnosis.supporting_evidence)
    ? (diagnosis.supporting_evidence as unknown[]).map(String)
    : [];
  const risks = Array.isArray(diagnosis.risk_factors)
    ? (diagnosis.risk_factors as unknown[]).map(String)
    : [];

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-medium text-ink">{rootCauseLabel(rootCause)}</div>
        <div className="font-mono text-[10px] text-ink-faint">{rootCause}</div>
      </div>

      <ConfidenceBar probability={probability} />

      {evidence.length > 0 ? (
        <div className="space-y-1">
          <div className="text-xs text-ink-faint">Supporting evidence</div>
          <ul className="space-y-1">
            {evidence.map((item) => (
              <li key={item} className="flex gap-2 text-xs text-ink-muted">
                <span className="text-brand">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {risks.length > 0 ? (
        <div className="space-y-1">
          <div className="text-xs text-ink-faint">Risk factors</div>
          <ul className="space-y-1">
            {risks.map((item) => (
              <li key={item} className="flex gap-2 text-xs text-warning">
                <span>⚠</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function MetaBadge({ label }: { label: string }) {
  return (
    <span className="rounded-4xl bg-subtle px-2 py-0.5 text-[10px] text-ink-muted">{label}</span>
  );
}

/**
 * The message as the customer would have seen it.
 *
 * The "Simulated" label is not decoration. Every adapter in Phase 5 writes an
 * attempt row and calls nothing, and a bubble that looked like a sent WhatsApp
 * message with no such marker would be the one place in this UI that implies
 * something happened when it did not.
 */
function ExecuteDetail({ attempt }: { attempt: ExecutionAttempt }) {
  const body = String(attempt.request_payload?.body ?? "");
  const generation = attempt.response_payload?.message_generation as
    | Record<string, unknown>
    | undefined;

  if (!body) return null;

  const tone = generation?.tone ? String(generation.tone) : null;
  const language = generation?.language ? String(generation.language) : null;
  const reasoning = generation?.generation_reasoning
    ? String(generation.generation_reasoning)
    : null;

  return (
    <div className="space-y-2">
      <div className="relative max-w-md rounded-lg rounded-tr-sm bg-[#dcf8c6] px-3 py-2 dark:bg-[#1f3320]">
        <span className="absolute top-1.5 right-2 text-[9px] font-medium text-warning">
          Simulated
        </span>
        <p className="pr-14 text-sm whitespace-pre-wrap text-[#111b21] dark:text-[#e9edef]">
          {body}
        </p>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {tone ? <MetaBadge label={humanise(tone)} /> : null}
        {language ? <MetaBadge label={humanise(language)} /> : null}
        <MetaBadge label={attempt.adapter} />
      </div>

      {reasoning ? <p className="text-xs text-ink-faint italic">{reasoning}</p> : null}
    </div>
  );
}

function ListenDetail({
  details,
  reply,
}: {
  details: Record<string, unknown>;
  reply: CustomerReply | null;
}) {
  // The classification on the reply row is the full ListenResult; the audit row
  // is a summary of it. Prefer the former, fall back to the latter.
  const classification = (reply?.llm_classification ?? details) as Record<string, unknown>;
  const intent = String(classification.intent ?? details.intent ?? "unknown");
  const optOut = Boolean(classification.opt_out_signal ?? details.opt_out_signal);
  const hardship = Boolean(classification.hardship_signal ?? details.hardship_signal);
  const churn = Boolean(classification.churn_signal ?? details.churn_signal);
  const entities = (classification.extracted_entities ?? {}) as Record<string, unknown>;
  const named = Object.entries(entities).filter(([, value]) => value !== null && value !== "");

  return (
    <div className="space-y-2">
      {reply ? (
        <div className="max-w-md rounded-lg rounded-tl-sm border border-hairline bg-elevated px-3 py-2">
          <p className="text-sm whitespace-pre-wrap text-ink">{reply.raw_text}</p>
          <div className="mt-1 text-[10px] text-ink-faint">via {reply.channel}</div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded-4xl bg-brand-subtle px-2 py-0.5 text-[10px] font-medium text-brand">
          {INTENT_LABELS[intent] ?? humanise(intent)}
        </span>
        <span className="font-mono text-[10px] text-ink-faint">{intent}</span>
      </div>

      {named.length > 0 ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
          {named.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-ink-faint">{ENTITY_LABELS[key] ?? humanise(key)}</dt>
              <dd className="text-ink-muted">{String(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {optOut ? (
        <div className="rounded-lg border border-danger bg-danger-subtle px-3 py-2 text-xs font-medium text-danger">
          ⛔ Opt-out honored — consent revoked across all channels
        </div>
      ) : null}

      {hardship ? (
        <div className="rounded-lg border border-warning bg-warning-subtle px-3 py-2 text-xs font-medium text-warning">
          ⚠️ Hardship detected — recovery paused, human handoff
        </div>
      ) : null}

      {churn ? (
        <div className="rounded-lg border border-warning bg-warning-subtle px-3 py-2 text-xs font-medium text-warning">
          🔁 Churn confirmed — handed to the retention team, nothing auto-cancelled
        </div>
      ) : null}
    </div>
  );
}

export function CaseTimeline({ caseDetail }: { caseDetail: CaseDetail }) {
  const byStep = new Map<string, AuditEvent[]>();
  for (const event of caseDetail.audit_events) {
    const step = event.event.split(":")[0];
    byStep.set(step, [...(byStep.get(step) ?? []), event]);
  }

  const stepsToShow = STEP_ORDER.filter((step) => byStep.has(step));

  // The richer payloads the audit summaries omit. Each is the most recent one,
  // because the timeline collapses repeated steps onto their final outcome.
  const diagnosis = caseDetail.diagnosis;
  // The decide row carries the full arm ranking and the context vector; the
  // audit summary carries neither. Newest first — a case worked over several
  // passes has several decide rows, and the timeline shows the latest outcome.
  const decideRow: AgentDecision | null =
    [...caseDetail.agent_decisions].reverse().find((d) => d.step_name === "decide") ?? null;
  const contextBucket = decideRow ? buildContextBucket(decideRow.bandit_context_vector) : null;
  const messageAttempt =
    [...caseDetail.execution_attempts]
      .reverse()
      .find((attempt) => Boolean(attempt.request_payload?.body)) ?? null;
  const classifiedReply =
    [...caseDetail.customer_replies]
      .reverse()
      .find((reply) => reply.llm_classification !== null) ??
    caseDetail.customer_replies[caseDetail.customer_replies.length - 1] ??
    null;

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

        let badge: ReactNode = null;
        if (stepName === "diagnose" && outcome.details) {
          badge = <ProvenanceBadge isStub={outcome.details.is_stub !== false} />;
        } else if (stepName === "decide" && decideRow) {
          badge = <DecideBadge decision={decideRow} contextBucket={contextBucket} />;
        }

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
                badge={badge}
              >
                {stepName === "diagnose" && diagnosis ? (
                  <DiagnoseDetail diagnosis={diagnosis} />
                ) : null}

                {stepName === "decide" && decideRow?.bandit_alternatives ? (
                  <BanditAlternativesFan
                    alternatives={decideRow.bandit_alternatives}
                    banditMode={decideRow.bandit_mode}
                    contextBucket={contextBucket}
                  />
                ) : null}

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

                {stepName === "execute" && messageAttempt ? (
                  <ExecuteDetail attempt={messageAttempt} />
                ) : null}

                {stepName === "listen" && outcome.details?.intent ? (
                  <ListenDetail details={outcome.details} reply={classifiedReply} />
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
