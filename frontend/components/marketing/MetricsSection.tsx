"use client";

import { AnimatedNumber, AnimatedPercent } from "@/components/ui/AnimatedNumber";
import { StaggerItem, StaggerList } from "@/components/ui/StaggerList";

/**
 * The four measured figures, from a 1,000-case batch run.
 *
 * `/app/batch` computes these; this quotes them. Every one is labelled with the
 * denominator it was measured against — "per 1,000 cases" rather than a bare
 * rupee figure — because a number without its denominator is a number the
 * reader will supply their own denominator for, and theirs will be wrong.
 */
const METRICS = [
  { key: "rate", label: "recovery rate" },
  { key: "incremental", label: "incremental, per 1,000 cases" },
  { key: "violations", label: "compliance violations" },
  { key: "detection", label: "to detect a bank outage" },
] as const;

/**
 * Section five, on the gold ground.
 *
 * The one band on the page that is neither the paper surface nor the ink one.
 * It is here because five alternating dark/light sections start to read as a
 * pattern the reader stops seeing; a third colour, used exactly once, is what
 * makes the numbers land as the point of the page rather than as another band.
 */
export function MetricsSection() {
  return (
    <section id="results" className="scroll-mt-24 bg-gold-light py-24 sm:py-28">
      <StaggerList
        as="ul"
        stagger={0.08}
        className="mx-auto grid max-w-6xl gap-y-12 px-6 sm:grid-cols-2 lg:grid-cols-4"
      >
        {METRICS.map((metric) => (
          <StaggerItem key={metric.key} as="li" className="text-center">
            <p className="font-display text-[clamp(48px,6vw,72px)] leading-none font-bold tracking-[-0.04em] text-ink tabular-nums">
              {metric.key === "rate" ? (
                <AnimatedPercent value={0.352} startOnView duration={1.6} />
              ) : metric.key === "incremental" ? (
                <AnimatedNumber
                  value={9.2}
                  startOnView
                  duration={1.6}
                  format={(n) => `₹${n.toFixed(1)}L`}
                />
              ) : metric.key === "detection" ? (
                <AnimatedNumber
                  value={91}
                  startOnView
                  duration={1.6}
                  format={(n) => `${Math.round(n)}s`}
                />
              ) : (
                "0"
              )}
            </p>
            <p className="mt-3 text-base font-medium text-ink-muted">{metric.label}</p>
          </StaggerItem>
        ))}
      </StaggerList>
    </section>
  );
}
