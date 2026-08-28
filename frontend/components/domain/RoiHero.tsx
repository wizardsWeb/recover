"use client";

/**
 * The two numbers, side by side.
 *
 * The hierarchy is the argument. Gross recovery is the figure every other
 * recovery dashboard leads with, so it is rendered first and deliberately
 * quieter — present, checkable, not the headline. Incremental recovery is
 * larger and in the brand colour because it is the number that survives the
 * question "would they have paid anyway?".
 *
 * Client-side only for the count-up. `AnimatedINR` writes to the DOM through a
 * `MotionValue`, so the figure animates without a React render per frame, and
 * it degrades to the settled value under `prefers-reduced-motion`.
 */

import { ArrowRight, Info } from "lucide-react";

import { AnimatedINR } from "@/components/ui/AnimatedNumber";
import type { UpliftRoi } from "@/lib/api/roi";
import { formatINR, formatPercent } from "@/lib/utils/format";

function Caption({ children }: { children: React.ReactNode }) {
  return <p className="mt-2 max-w-xs text-xs leading-relaxed text-ink-muted">{children}</p>;
}

export function RoiHero({ roi }: { roi: UpliftRoi }) {
  const { gross_recovery_cents: gross, incremental_recovery_cents: incremental } = roi;

  return (
    <section className="rounded-lg border border-hairline p-5 sm:p-6">
      <div className="grid gap-8 sm:grid-cols-[1fr_auto_1fr] sm:items-start sm:gap-6">
        <div>
          <h2 className="text-[10px] font-medium tracking-wide text-ink-faint uppercase">
            Gross recovered
          </h2>
          <p className="mt-1 font-mono text-4xl tabular-nums text-ink-muted">
            {formatINR(gross)}
          </p>
          <Caption>
            Every rupee recovered on a case the agent worked — including from customers who
            would have paid regardless.
          </Caption>
        </div>

        <div
          aria-hidden
          className="hidden self-center text-ink-faint sm:block print:hidden"
        >
          <ArrowRight size={20} />
        </div>

        <div>
          <h2 className="text-[10px] font-medium tracking-wide text-brand uppercase">
            Incremental — caused by the agent
          </h2>
          {roi.is_estimable && incremental !== null ? (
            <>
              <AnimatedINR
                value={incremental}
                startOnView
                className="mt-1 block font-mono text-5xl leading-none tabular-nums text-brand"
              />
              <Caption>
                {roi.incremental_pct_of_gross !== null ? (
                  <>
                    <strong className="font-medium text-ink">
                      {formatPercent(roi.incremental_pct_of_gross)}
                    </strong>{" "}
                    of gross. The rest would have arrived without a message — the holdout group
                    is how we know.
                  </>
                ) : (
                  <>Measured against the cases the agent deliberately left alone.</>
                )}
              </Caption>
            </>
          ) : (
            <>
              <p className="mt-1 font-mono text-5xl leading-none text-ink-faint">—</p>
              <Caption>
                <span className="inline-flex items-start gap-1.5">
                  <Info size={13} className="mt-0.5 shrink-0" />
                  <span>
                    Not estimable yet. Without resolved holdout cases there is nothing to
                    compare against, and a number here would be a guess.
                  </span>
                </span>
              </Caption>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
