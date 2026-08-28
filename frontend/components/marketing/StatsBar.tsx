"use client";

import { AnimatedPercent } from "@/components/ui/AnimatedNumber";

/**
 * The three claims, on one rule.
 *
 * Only the recovery rate counts up. It is the measured number and the one the
 * page is asking to be believed; the other two are facts about the product
 * rather than results, and animating a zero is a no-op that would draw the eye
 * to the least interesting figure on the line.
 *
 * The count is held until the bar scrolls into view — a stat that finished
 * animating above the fold is, to the reader who arrives at it, static.
 */
export function StatsBar() {
  return (
    <section className="border-y border-hairline bg-subtle">
      <dl className="mx-auto flex max-w-6xl flex-col divide-y divide-hairline px-6 sm:flex-row sm:divide-x sm:divide-y-0">
        <div className="flex-1 py-8 text-center sm:px-8">
          <dt className="sr-only">Recovery rate</dt>
          <dd>
            <span className="font-display text-4xl font-medium tracking-[-0.03em] text-brand tabular-nums">
              <AnimatedPercent value={0.352} startOnView duration={1.4} />
            </span>
            <span className="mt-1 block text-sm text-ink-muted">recovery rate</span>
          </dd>
        </div>

        <div className="flex-1 py-8 text-center sm:px-8">
          <dt className="sr-only">Compliance violations</dt>
          <dd>
            <span className="font-display text-4xl font-medium tracking-[-0.03em] text-ink tabular-nums">
              0
            </span>
            <span className="mt-1 block text-sm text-ink-muted">compliance violations</span>
          </dd>
        </div>

        <div className="flex-1 py-8 text-center sm:px-8">
          <dt className="sr-only">Playbooks</dt>
          <dd>
            <span className="font-display text-4xl font-medium tracking-[-0.03em] text-ink tabular-nums">
              4
            </span>
            <span className="mt-1 block text-sm text-ink-muted">playbooks, one agent</span>
          </dd>
        </div>
      </dl>
    </section>
  );
}
