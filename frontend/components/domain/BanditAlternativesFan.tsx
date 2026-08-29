"use client";

import { motion, useReducedMotion } from "framer-motion";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
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

/**
 * Seconds added per bar. The fan reads top to bottom, and 50ms is fast enough
 * that six arms finish inside a third of a second — long enough to see the
 * ranking sweep out, short enough that nobody waits for it.
 */
const STAGGER = 0.05;

function armLabel(arm: string): string {
  return arm.replace(/_/g, " ");
}

export function BanditAlternativesFan({ alternatives, banditMode, contextBucket }: Props) {
  const prefersReducedMotion = useReducedMotion();

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
            // A real tooltip rather than `title`: what is in it — why this arm
            // lost, what it drew this round, how much history it has — is the
            // argument for the decision, and a native tooltip cannot be reached
            // by keyboard at all.
            <Tooltip key={alt.arm_name}>
              <TooltipTrigger
                render={<div className="flex items-center gap-2" tabIndex={tooltip ? 0 : -1} />}
              >
              <span
                className={`w-[110px] shrink-0 truncate xl:w-[180px] font-mono text-[11px] ${
                  alt.chosen ? "font-semibold text-ink" : "text-ink-faint"
                }`}
              >
                {armLabel(alt.arm_name)}
              </span>

              {/* Framer drives the width rather than a CSS transition off a
                  mounted flag: `initial` gives it the zero-width start state
                  without a render pass whose only job is to be replaced one
                  frame later. */}
              <div className="h-2 flex-1 overflow-hidden rounded-none bg-inset">
                <motion.div
                  className={`h-full min-w-[2px] rounded-none ${
                    alt.chosen ? "bg-brand" : alt.is_cold ? "bg-hairline" : "bg-ink-faint/40"
                  }`}
                  initial={{ width: prefersReducedMotion ? `${pct}%` : 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={
                    prefersReducedMotion
                      ? { duration: 0 }
                      : { duration: 0.4, ease: "easeOut", delay: index * STAGGER }
                  }
                />
              </div>

              <span
                className={`w-10 shrink-0 text-right font-mono text-[11px] tabular-nums ${
                  alt.chosen ? "text-ink" : "text-ink-faint"
                }`}
              >
                {alt.is_cold ? "—" : `${pct}%`}
              </span>
              </TooltipTrigger>
              {tooltip ? <TooltipContent>{tooltip}</TooltipContent> : null}
            </Tooltip>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {contextBucket ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <span
                  tabIndex={0}
                  className="rounded-none bg-subtle px-2 py-0.5 font-mono text-[10px] text-ink-muted"
                />
              }
            >
              {contextBucket}
            </TooltipTrigger>
            <TooltipContent>
              Arms are learned per context — bank, method, time of day, LTV band
            </TooltipContent>
          </Tooltip>
        ) : null}

        {banditMode === "explore" ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <span
                  tabIndex={0}
                  className="rounded-none bg-info-subtle px-2 py-0.5 text-[10px] font-medium text-info"
                />
              }
            >
              Explore
            </TooltipTrigger>
            <TooltipContent>
              This arm&rsquo;s draw beat an arm with a higher mean — the pull buys information
            </TooltipContent>
          </Tooltip>
        ) : banditMode === "exploit" ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <span
                  tabIndex={0}
                  className="rounded-none bg-brand-subtle px-2 py-0.5 text-[10px] font-medium text-brand"
                />
              }
            >
              Exploit
            </TooltipTrigger>
            <TooltipContent>
              This arm has both the best draw and the standing evidence
            </TooltipContent>
          </Tooltip>
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
