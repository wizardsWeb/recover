"use client";

/**
 * The two numbers, side by side.
 *
 * The hierarchy is the argument. Gross recovery is the figure every other
 * recovery dashboard leads with, so it is rendered first and deliberately
 * quieter — present, checkable, not the headline. Incremental recovery is
 * larger, in the brand colour, and carries the page's one gold line, because it
 * is the number that survives the question "would they have paid anyway?".
 *
 * Gold appears exactly once on this page and it is here. The brief also asked
 * for a gold border on the persuadable bucket card; two golds on one screen
 * makes neither of them read as the answer, so that card is marked with the
 * brand instead. This is the sentence the page exists to say.
 *
 * Client-side only for the count-up. `AnimatedINR` writes to the DOM through a
 * `MotionValue`, so the figure animates without a React render per frame, and
 * it degrades to the settled value under `prefers-reduced-motion`.
 */

import { Info } from "lucide-react";

import { AnimatedINR } from "@/components/ui/AnimatedNumber";
import { Card, CardContent } from "@/components/ui/card";
import type { UpliftRoi } from "@/lib/api/roi";
import { formatINR, formatPercent } from "@/lib/utils/format";

function Caption({ children }: { children: React.ReactNode }) {
  return <p className="mt-3 max-w-xs text-xs leading-relaxed text-ink-muted">{children}</p>;
}

export function RoiHero({ roi }: { roi: UpliftRoi }) {
  const { gross_recovery_cents: gross, incremental_recovery_cents: incremental } = roi;

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Card className="border-hairline shadow-card">
        <CardContent className="p-5 sm:p-6">
          <h2 className="text-[11px] font-medium tracking-[0.06em] text-ink-faint uppercase">
            Gross recovered
          </h2>
          {/* Inter, not the display face, and at 36px. The quieter setting is
              the point: this is the number the reader is being asked to look
              past, and matching the headline's typeface would make them
              equals. */}
          <p className="mt-2 text-4xl leading-none font-normal text-ink-muted tabular-nums">
            {formatINR(gross)}
          </p>
          <Caption>
            Every rupee recovered on a case the agent worked — including from customers who would
            have paid regardless.
          </Caption>
        </CardContent>
      </Card>

      <Card className="border-hairline shadow-card">
        <CardContent className="p-5 sm:p-6">
          <h2 className="text-[11px] font-medium tracking-[0.06em] text-brand uppercase">
            Incremental
          </h2>
          {roi.is_estimable && incremental !== null ? (
            <>
              <AnimatedINR
                value={incremental}
                startOnView
                className="mt-2 block font-display text-[52px] leading-none font-bold tracking-[-0.03em] text-brand tabular-nums"
              />
              <p className="mt-1.5 text-sm font-medium text-gold">what we truly earned</p>
              <Caption>
                {roi.incremental_pct_of_gross !== null ? (
                  <>
                    <strong className="font-medium text-ink">
                      {formatPercent(roi.incremental_pct_of_gross)}
                    </strong>{" "}
                    of gross. The rest would have arrived without a message — the holdout group is
                    how we know.
                  </>
                ) : (
                  <>Measured against the cases the agent deliberately left alone.</>
                )}
              </Caption>
            </>
          ) : (
            <>
              <p className="mt-2 font-display text-[52px] leading-none font-bold text-ink-faint">
                —
              </p>
              <Caption>
                <span className="inline-flex items-start gap-1.5">
                  <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  <span>
                    Not estimable yet. Without resolved holdout cases there is nothing to compare
                    against, and a number here would be a guess.
                  </span>
                </span>
              </Caption>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
