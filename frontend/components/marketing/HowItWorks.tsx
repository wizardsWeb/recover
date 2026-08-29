"use client";

import { Cpu, Eye, ShieldCheck } from "lucide-react";

import { RazorpayGlyph } from "@/components/brand/RazorpayGlyph";
import type { LucideIcon } from "lucide-react";
import { motion, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import { useRef } from "react";

interface Step {
  icon: LucideIcon;
  title: string;
  body: string;
}

const STEPS: Step[] = [
  {
    icon: Eye,
    title: "Detects",
    body: "Watches every Razorpay webhook in real time — payment, subscription, invoice, checkout.",
  },
  {
    icon: Cpu,
    title: "Decides",
    body: "A contextual bandit learns what works per customer, bank, and hour, and picks accordingly.",
  },
  {
    icon: ShieldCheck,
    title: "Recovers",
    body: "Executes through Razorpay rails. Consent, quiet hours and frequency checked first, every action auditable.",
  },
];

/**
 * The Razorpay products the agent actually calls, in the order the playbooks
 * use them. Payment Links and Subscriptions are real calls today; the Payment
 * Gateway is where the webhooks come *from*, which is why it is named as a rail
 * rather than as something the agent invokes.
 */
const RAILS = [
  "Payment Gateway",
  "Payment Links",
  "Subscriptions",
  "RazorpayX",
];

/**
 * Section three: the loop, in three beats.
 *
 * The connector draws itself as the reader scrolls rather than on mount. Tying
 * it to `scrollYProgress` is what makes it feel like the reader is drawing it —
 * an on-mount animation would have finished before most people reached the
 * section, and would be doing its work for an empty room.
 *
 * `useSpring` sits between the scroll value and `pathLength` so the line has
 * some mass. Bound directly, the stroke tracks a trackpad's every jitter and
 * reads as a progress bar; through a spring it lags slightly and reads as ink.
 *
 * The offsets say: start drawing when the section's top reaches 75% down the
 * viewport, finish when its middle is a little above centre. That is roughly
 * one comfortable scroll gesture, so the line completes as the third step
 * becomes readable rather than long before or after it.
 */
export function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null);
  const prefersReducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 75%", "center 45%"],
  });
  const smoothed = useSpring(scrollYProgress, { stiffness: 120, damping: 30, restDelta: 0.001 });
  // Reduced motion gets the finished line rather than no line: the connector is
  // information — it says these three things happen in order — and withholding
  // it would remove meaning rather than movement.
  const pathLength = useTransform(prefersReducedMotion ? scrollYProgress : smoothed, (value) =>
    prefersReducedMotion ? 1 : value,
  );

  return (
    <section id="how-it-works" className="scroll-mt-24 bg-base py-24 sm:py-32">
      <div className="mx-auto max-w-6xl px-6">
        <h2 className="max-w-2xl font-display text-4xl leading-[1.1] font-semibold tracking-[-0.03em] text-ink sm:text-5xl">
          Three beats, on every case.
        </h2>
        <p className="mt-4 max-w-xl text-base leading-relaxed text-ink-muted">
          The agent runs the same loop whether the leak is a failed card or a ninety-day invoice.
          What changes is what it learns between one case and the next.
        </p>

        <div ref={ref} className="relative mt-16">
          {/* ---- The connector ---------------------------------------------
              Two SVGs rather than one rotated element: the horizontal line
              spans the gaps between three columns and the vertical one runs
              down a single stacked column, which are different geometries and
              not the same line at 90°. Both read the same motion value, so
              there is still only one source of progress.

              `aria-hidden`: the order is already in the step numbers. */}
          <svg
            aria-hidden
            className="pointer-events-none absolute top-6 right-0 left-0 hidden h-0.5 w-full md:block"
            preserveAspectRatio="none"
            viewBox="0 0 100 2"
          >
            <line x1="0" y1="1" x2="100" y2="1" stroke="var(--border-subtle)" strokeWidth="2" />
            <motion.line
              x1="0"
              y1="1"
              x2="100"
              y2="1"
              stroke="var(--brand)"
              strokeWidth="2"
              style={{ pathLength }}
            />
          </svg>
          <svg
            aria-hidden
            className="pointer-events-none absolute top-6 bottom-6 left-6 w-0.5 md:hidden"
            preserveAspectRatio="none"
            viewBox="0 0 2 100"
          >
            <line x1="1" y1="0" x2="1" y2="100" stroke="var(--border-subtle)" strokeWidth="2" />
            <motion.line
              x1="1"
              y1="0"
              x2="1"
              y2="100"
              stroke="var(--brand)"
              strokeWidth="2"
              style={{ pathLength }}
            />
          </svg>

          <ol className="relative grid gap-12 md:grid-cols-3 md:gap-8">
            {STEPS.map((step, index) => {
              const Icon = step.icon;
              return (
                <li key={step.title} className="md:pr-6">
                  {/* The circle's own background is what breaks the connector
                      behind it — without it the line runs straight through the
                      numeral. */}
                  <span className="flex size-12 items-center justify-center rounded-full border border-hairline bg-base font-display text-lg font-bold text-brand tabular-nums">
                    {index + 1}
                  </span>
                  <Icon className="mt-7 size-10 text-ink-faint" strokeWidth={1.25} aria-hidden />
                  <h3 className="mt-5 font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
                    {step.title}
                  </h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">{step.body}</p>
                </li>
              );
            })}
          </ol>
        </div>

        {/* ---- What it executes through ----------------------------------
            The claim the three steps above are only credible with. "Recovers"
            means nothing until it says through what — and naming the four
            products is more specific, and therefore more checkable, than a
            logo on its own. */}
        <div className="mt-16 flex flex-wrap items-center gap-x-4 gap-y-3 border-t border-hairline pt-8">
          <span className="flex items-center gap-2">
            <RazorpayGlyph className="size-5" title="Razorpay" />
            <span className="text-sm font-medium text-ink">Executes through Razorpay rails</span>
          </span>
          <ul className="flex flex-wrap items-center gap-2">
            {RAILS.map((rail) => (
              <li
                key={rail}
                className="rounded-4xl border border-hairline bg-elevated px-2.5 py-1 text-[11px] font-medium text-ink-muted"
              >
                {rail}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
