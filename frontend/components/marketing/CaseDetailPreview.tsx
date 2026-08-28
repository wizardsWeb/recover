import { Cpu, Ear, GitBranch, Search, Shield, Zap } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * A miniature of the case detail screen, for the hero.
 *
 * Real markup in the dashboard's own idiom rather than a screenshot: it stays
 * sharp at any density, re-themes with the rest of the page, and cannot drift
 * into showing a version of the product that no longer exists — a captured PNG
 * goes stale the first time the timeline changes and nobody notices.
 *
 * The figures are one of the seeded demo personas, not a merchant's data. It is
 * labelled as an example so a visitor never reads it as a live console.
 */

interface PreviewStep {
  icon: LucideIcon;
  label: string;
  detail: string;
  tone: "done" | "brand" | "muted";
}

const STEPS: PreviewStep[] = [
  {
    icon: Search,
    label: "Detect",
    detail: "Mandate failed · ICICI · UPI",
    tone: "done",
  },
  {
    icon: GitBranch,
    label: "Diagnose",
    detail: "Salary-cycle mismatch — 3 failures on the 1st",
    tone: "done",
  },
  {
    icon: Cpu,
    label: "Decide",
    detail: "Retry on the 7th + WhatsApp fallback",
    tone: "brand",
  },
  {
    icon: Shield,
    label: "Guardrail",
    detail: "Consent ✓ · Quiet hours ✓ · Frequency ✓",
    tone: "done",
  },
  { icon: Zap, label: "Execute", detail: "₹2,999 recovered", tone: "done" },
  { icon: Ear, label: "Listen", detail: "Awaiting reply", tone: "muted" },
];

const TONES: Record<PreviewStep["tone"], string> = {
  done: "bg-success-subtle text-success",
  brand: "bg-brand-subtle text-brand",
  muted: "bg-subtle text-ink-faint",
};

export function CaseDetailPreview() {
  return (
    <figure className="w-full max-w-md">
      <div className="overflow-hidden rounded-xl border border-hairline bg-elevated shadow-sm">
        <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
          <div>
            <div className="font-display text-sm font-semibold text-ink">Case 7F3A21C8</div>
            <div className="text-[11px] text-ink-faint">Suresh K. · subscription failure</div>
          </div>
          <span className="rounded-4xl bg-success-subtle px-2 py-0.5 text-[10px] font-medium text-success">
            Recovered
          </span>
        </div>

        <div className="space-y-2 px-4 py-4">
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            const isLast = index === STEPS.length - 1;
            return (
              <div key={step.label} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div
                    className={`flex size-6 shrink-0 items-center justify-center rounded-full ${TONES[step.tone]}`}
                  >
                    <Icon size={12} aria-hidden />
                  </div>
                  {!isLast ? <div className="my-1 w-px flex-1 bg-hairline" /> : null}
                </div>
                <div className="min-w-0 flex-1 pb-1">
                  <div className="text-xs font-medium text-ink">{step.label}</div>
                  <div className="truncate text-[11px] text-ink-muted">{step.detail}</div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-between border-t border-hairline bg-subtle px-4 py-2.5">
          <span className="text-[11px] text-ink-faint">At risk ₹2,999</span>
          <span className="font-mono text-[11px] font-medium text-success">+ ₹2,999</span>
        </div>
      </div>

      <figcaption className="mt-3 text-center text-xs text-ink-faint">
        An example case — every step the agent took, and why.
      </figcaption>
    </figure>
  );
}
