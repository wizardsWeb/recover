"use client";

import { Braces, GitBranch, Languages, ShieldCheck, Sparkles, Zap } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { useRef } from "react";

interface TimelineStep {
  icon: LucideIcon;
  label: string;
  detail: string;
  tone: "done" | "brand";
}

const STEPS: TimelineStep[] = [
  { icon: Zap, label: "Detect", detail: "Mandate failed · ICICI · UPI", tone: "done" },
  { icon: GitBranch, label: "Diagnose", detail: "3 failures, all on the 1st", tone: "done" },
  { icon: Sparkles, label: "Decide", detail: "Retry on the 7th + WhatsApp", tone: "brand" },
  { icon: ShieldCheck, label: "Guardrail", detail: "Consent ✓ Quiet hours ✓", tone: "done" },
];

const CALLOUTS: Array<{ icon: LucideIcon; title: string; body: string }> = [
  {
    icon: Braces,
    title: "Causal DAG diagnosis",
    body: "Bayesian traversal over a per-playbook graph, not a prompt asking a model to guess.",
  },
  {
    icon: Sparkles,
    title: "Contextual bandit decisions",
    body: "Thompson sampling per arm, conditioned on customer, bank and hour of day.",
  },
  {
    icon: Languages,
    title: "Hinglish reply intelligence",
    body: "Reads “salary aane ke baad karta hoon” as a promise to pay, and schedules for it.",
  },
];

/**
 * Section four: the console, recreated in markup.
 *
 * Real HTML in the dashboard's own idiom rather than a screenshot. It stays
 * sharp at any density, re-themes with the reader's own colour mode, and cannot
 * drift into showing a version of the product that no longer exists — a
 * captured PNG goes stale the first time the timeline changes and nobody
 * notices for six months.
 *
 * The parallax is 60px over the whole scroll of the section, which is small
 * enough that most readers will not consciously see it. That is the intent: it
 * separates the mockup from the callouts beside it by making them move at
 * different rates, which is depth rather than decoration.
 */
export function AgentSection() {
  const ref = useRef<HTMLDivElement>(null);
  const prefersReducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], [40, -40]);

  return (
    <section id="agent" ref={ref} className="scroll-mt-24 bg-ink-900 py-24 sm:py-32">
      <div className="mx-auto max-w-6xl px-6">
        <h2 className="max-w-2xl font-display text-[clamp(36px,5vw,56px)] leading-[1.05] font-bold tracking-[-0.03em] text-white">
          See the agent think.
        </h2>

        <div className="mt-14 grid items-center gap-12 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          <motion.div style={prefersReducedMotion ? undefined : { y }}>
            <ConsoleMockup />
          </motion.div>

          <ul className="space-y-8">
            {CALLOUTS.map(({ icon: Icon, title, body }) => (
              <li key={title} className="flex gap-4">
                <Icon
                  className="mt-0.5 size-6 shrink-0 text-brand-on-dark"
                  strokeWidth={1.5}
                  aria-hidden
                />
                <div>
                  <h3 className="font-display text-lg font-semibold tracking-[-0.01em] text-white">
                    {title}
                  </h3>
                  <p className="mt-1 text-sm leading-relaxed text-white/55">{body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

const TONES: Record<TimelineStep["tone"], string> = {
  done: "bg-success-subtle text-success",
  brand: "bg-brand-subtle text-brand",
};

/**
 * The browser chrome and what is inside it.
 *
 * Everything below the chrome bar is drawn with the product's own semantic
 * tokens, so the mockup renders in whichever mode the reader is in. It is a
 * picture of *their* console, not of ours.
 */
function ConsoleMockup() {
  return (
    <figure className="overflow-hidden rounded-xl border border-white/10 bg-elevated shadow-[0_24px_60px_rgb(0_0_0/0.45)]">
      {/* Chrome. The dots are decorative and carry no state — they are the
          three pixels that say "this is a browser" and nothing more. */}
      <div className="flex items-center gap-2 border-b border-hairline bg-subtle px-4 py-3">
        <span aria-hidden className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-danger/70" />
          <span className="size-2.5 rounded-full bg-warning/70" />
          <span className="size-2.5 rounded-full bg-success/70" />
        </span>
        <span className="mx-auto rounded-full bg-elevated px-3 py-1 font-mono text-[11px] text-ink-faint">
          recover.app/app/cases/7F3A21C8
        </span>
      </div>

      <div className="px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-display text-sm font-semibold text-ink">Suresh K.</p>
            <p className="font-mono text-[11px] text-ink-faint">
              case_7F3A21C8 · subscription_failure
            </p>
          </div>
          <span className="rounded-full bg-success-subtle px-2.5 py-0.5 text-[10px] font-medium text-success">
            Recovered
          </span>
        </div>

        {/* ---- The root cause ------------------------------------------------
            The one gold element on the whole landing page. Gold means "this is
            the answer the agent found"; if it also meant "warning" or "premium"
            it would mean nothing. */}
        <p className="mt-4 inline-flex items-center gap-2 rounded-full border border-gold bg-gold-light px-3 py-1 text-xs font-medium text-gold">
          <GitBranch className="size-3.5" strokeWidth={1.75} aria-hidden />
          Salary cycle mismatch · 0.82
        </p>

        <ol className="mt-5 space-y-2.5">
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            const last = index === STEPS.length - 1;
            return (
              <li key={step.label} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <span
                    className={`flex size-6 shrink-0 items-center justify-center rounded-full ${TONES[step.tone]}`}
                  >
                    <Icon className="size-3" strokeWidth={2} aria-hidden />
                  </span>
                  {!last && <span className="my-1 w-px flex-1 bg-hairline" />}
                </div>
                <div className="min-w-0 flex-1 pb-0.5">
                  <p className="text-xs font-medium text-ink">{step.label}</p>
                  <p className="truncate text-[11px] text-ink-muted">{step.detail}</p>
                </div>
              </li>
            );
          })}
        </ol>

        {/* ---- What actually went out ----------------------------------------
            WhatsApp's own outgoing-bubble green and its own corner geometry —
            square at the top left where the tail attaches, rounded elsewhere.
            The point of the shape is that a merchant recognises the channel
            before reading a word of it. */}
        <div className="mt-5 border-t border-hairline pt-4">
          <p className="flex items-center gap-1.5 text-[10px] font-medium tracking-[0.08em] text-ink-faint uppercase">
            <span aria-hidden className="size-2 rounded-full bg-whatsapp-brand" />
            Sent on WhatsApp
          </p>
          <p className="mt-2.5 max-w-[280px] rounded-[0_12px_12px_12px] bg-whatsapp-bubble px-3.5 py-2.5 text-sm leading-relaxed text-whatsapp-ink">
            Hi Suresh — your Zenith plan didn&rsquo;t renew on the 1st. Shall we try again on the
            7th, after payday?
          </p>
        </div>
      </div>

      <figcaption className="border-t border-hairline bg-subtle px-5 py-2.5 text-[11px] text-ink-faint">
        An example case. Every step the agent took, and why.
      </figcaption>
    </figure>
  );
}
