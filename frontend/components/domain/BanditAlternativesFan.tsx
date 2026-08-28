"use client";

import { useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

import type { BanditAlternative } from "@/lib/api/cases";

/**
 * Every arm the bandit weighed, and how far apart it thinks they are.
 *
 * The counterfactual is the point. "We sent an 8% discount" is an assertion;
 * "we sent 8% because it recovers 73% of carts like this one, against 64% for
 * 12% off and 31% for no discount at all" is an argument a merchant can check
 * and disagree with. Showing only the winner would make the agent's reasoning
 * exactly as inspectable as a coin flip.
 *
 * **Bars show the posterior mean, not the sampled draw.** The draw is what
 * decided this one case and it is deliberately random; the mean is what the
 * agent has actually learned. A merchant reading the chart wants the belief.
 * The draw is on the hover tooltip for anyone checking why the highest bar did
 * not always win — which is the explore case, and is labelled as such.
 *
 * Cold arms are drawn differently rather than shown at 50%. An arm with no
 * history has a mean of 0.5 by construction, and rendering that as a half-full
 * bar beside arms with real evidence invents a measurement that does not exist.
 */

interface Props {
  alternatives: BanditAlternative[];
  banditMode: "exploit" | "explore" | null;
  contextBucket: string | null;
}

/** Mount animation: bars grow from zero, staggered down the list. */
const STAGGER_MS = 40;

function armLabel(arm: string): string {
  return arm.replace(/_/g, " ");
}

export function BanditAlternativesFan({ alternatives, banditMode, contextBucket }: Props) {
  const [mounted, setMounted] = useState(false);
  const prefersReducedMotion = useReducedMotion();

  // One frame after mount, so the transition has a zero-width start state to
  // animate away from. Setting the final width on the first paint would render
  // the bars complete with no motion at all.
  useEffect(() => {
    const frame = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  if (alternatives.length === 0) return null;

  // Ranked by belief, not by draw — the same order the bars are read in.
  const ranked = [...alternatives].sort((a, b) => b.expected_reward - a.expected_reward);

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        {ranked.map((alt, index) => {
          const pct = Math.round(Math.max(0, Math.min(1, alt.expected_reward)) * 100);
          const tooltip = [
            alt.not_chosen_reason,
            alt.sampled_theta != null ? `Drew ${alt.sampled_theta.toFixed(3)} this round` : null,
            alt.n_pulls != null ? `${alt.n_pulls} past pulls` : null,
          ]
            .filter(Boolean)
            .join(" · ");

          return (
            <div key={alt.arm_name} className="flex items-center gap-2" title={tooltip}>
              <span
                className={`w-[180px] shrink-0 truncate font-mono text-[11px] ${
                  alt.chosen ? "font-semibold text-ink" : "text-ink-faint"
                }`}
              >
                {armLabel(alt.arm_name)}
              </span>

              <div className="h-2 flex-1 overflow-hidden rounded-4xl bg-inset">
                <div
                  className={`h-full min-w-[2px] rounded-4xl ${
                    prefersReducedMotion ? "" : "transition-[width] duration-300 ease-out"
                  } ${
                    alt.chosen
                      ? "bg-brand"
                      : alt.is_cold
                        ? "bg-hairline"
                        : "bg-ink-faint/40"
                  }`}
                  style={{
                    width: mounted || prefersReducedMotion ? `${pct}%` : "0%",
                    transitionDelay: prefersReducedMotion
                      ? undefined
                      : `${index * STAGGER_MS}ms`,
                  }}
                />
              </div>

              <span
                className={`w-10 shrink-0 text-right font-mono text-[11px] tabular-nums ${
                  alt.chosen ? "text-ink" : "text-ink-faint"
                }`}
              >
                {alt.is_cold ? "—" : `${pct}%`}
              </span>
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {contextBucket ? (
          <span
            className="rounded-4xl bg-subtle px-2 py-0.5 font-mono text-[10px] text-ink-muted"
            title="Arms are learned per context — bank, method, time of day, LTV band"
          >
            {contextBucket}
          </span>
        ) : null}

        {banditMode === "explore" ? (
          <span
            className="rounded-4xl bg-info-subtle px-2 py-0.5 text-[10px] font-medium text-info"
            title="This arm's draw beat an arm with a higher mean — the pull buys information"
          >
            Explore
          </span>
        ) : banditMode === "exploit" ? (
          <span
            className="rounded-4xl bg-brand-subtle px-2 py-0.5 text-[10px] font-medium text-brand"
            title="This arm has both the best draw and the standing evidence"
          >
            Exploit
          </span>
        ) : null}

        {ranked.some((alt) => alt.is_cold) ? (
          <span className="text-[10px] text-ink-faint">
            — arms marked “—” have no history in this context yet
          </span>
        ) : null}
      </div>
    </div>
  );
}
