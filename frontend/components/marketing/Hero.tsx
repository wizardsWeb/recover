"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";

import { ScrollCue } from "@/components/marketing/ScrollCue";
import { TrustStrip } from "@/components/marketing/TrustStrip";
import { AnimatedNumber, AnimatedPercent } from "@/components/ui/AnimatedNumber";
import { HERO_VIDEO } from "@/lib/assets/images";
import { SPRING } from "@/lib/motion";

/** The headline, one array entry per rendered line. */
const HEADLINE = ["Every Rupee", "Has A Reason."];

/**
 * The three claims, on the pills under the subhead.
 *
 * These are the measured figures from a 1,000-case batch run — `/app/batch`
 * computes them and this quotes them — rounded, because a landing page claiming
 * 41.97% is a landing page nobody believes. `0` is not animated: counting to
 * zero is a no-op that would draw the eye to the least interesting figure on
 * the line.
 */
const STATS = [
  { key: "rate", label: "recovery rate" },
  { key: "violations", label: "compliance violations" },
  { key: "incremental", label: "incremental" },
] as const;

/**
 * The opening shot.
 *
 * A full-viewport loop behind a 70% scrim. The video is atmosphere, not
 * information — nothing in it needs to be read — which is what makes a scrim
 * that heavy the right call rather than a compromise: the copy sits at better
 * than 12:1 against the scrim whatever frame is underneath, so legibility never
 * depends on the video's luminance at a given moment.
 *
 * The headline is set in Bubbledot, a dot-matrix face, and is the only place in
 * the product that face appears. It is doing one job: a wall of Sora would read
 * as a well-made dashboard's landing page, and the point of the first two
 * seconds is that this is a *product*, not a deploy of a component library.
 *
 * Lines animate one at a time rather than as a block. The stagger is what makes
 * a two-line headline read as a sentence being spoken rather than as a slab
 * arriving — 0.15s is roughly the beat between them if you said it aloud.
 */
export function Hero() {
  const prefersReducedMotion = useReducedMotion();

  return (
    <section
      id="top"
      className="relative isolate flex min-h-dvh items-center overflow-hidden bg-ink-900"
    >
      <video
        className="absolute inset-0 -z-20 size-full object-cover"
        src={HERO_VIDEO.src}
        autoPlay
        loop
        muted
        playsInline
        // Decorative: the frame carries no information the copy does not, and a
        // background loop nobody can pause should never be in the tab order.
        aria-hidden
        tabIndex={-1}
      />
      <div aria-hidden className="absolute inset-0 -z-10 bg-black/70" />

      <div className="mx-auto w-full max-w-4xl px-6 py-32 text-center">
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.5 }}
          className="text-[11px] font-medium tracking-[0.15em] text-sidebar-gold uppercase"
        >
          Razorpay Buildathon 2026 · Track 03
        </motion.p>

        <h1 className="mt-7 font-dotmatrix text-[clamp(52px,8vw,96px)] leading-[1.08] tracking-[-0.04em] text-white">
          {HEADLINE.map((line, index) => (
            <motion.span
              key={line}
              className="block"
              initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 20 }}
              animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
              transition={
                prefersReducedMotion ? { duration: 0 } : { ...SPRING, delay: index * 0.15 }
              }
            >
              {line}
            </motion.span>
          ))}
        </h1>

        <p className="mx-auto mt-7 max-w-[560px] text-[clamp(16px,2vw,20px)] leading-relaxed text-white/75">
          An AI agent that watches your Razorpay event stream, diagnoses every leak, and wins
          revenue back — compliantly.
        </p>

        <ul className="mt-9 flex flex-wrap items-center justify-center gap-x-2 gap-y-2 text-sm">
          {STATS.map((stat, index) => (
            <li key={stat.key} className="flex items-center gap-2">
              {index > 0 && (
                <span aria-hidden className="text-sidebar-gold">
                  ·
                </span>
              )}
              <span className="rounded-full border border-white/15 bg-white/5 px-3.5 py-1.5">
                <span className="font-display font-semibold text-white tabular-nums">
                  {stat.key === "rate" ? (
                    <AnimatedPercent value={0.352} duration={1.4} />
                  ) : stat.key === "incremental" ? (
                    <AnimatedNumber value={9.2} format={(n) => `₹${n.toFixed(1)}L`} duration={1.4} />
                  ) : (
                    "0"
                  )}
                </span>{" "}
                <span className="text-white/70">{stat.label}</span>
              </span>
            </li>
          ))}
        </ul>

        {/* The one white-glow element on the page. It is the only thing a
            visitor is being asked to do, and a glow is what a dark hero has
            instead of a shadow — a drop shadow on black is invisible. */}
        <div className="mt-10 flex justify-center">
          <Link
            href="/signup"
            className="rounded-full bg-white px-7 py-3.5 text-base font-semibold text-ink-900 shadow-[0_0_22px_rgb(255_255_255/0.32),0_0_44px_rgb(255_255_255/0.12)] transition-transform duration-200 ease-out hover:-translate-y-0.5 hover:scale-[1.03] focus-visible:ring-3 focus-visible:ring-white/50 focus-visible:outline-none motion-reduce:transition-none motion-reduce:hover:translate-y-0 motion-reduce:hover:scale-100"
          >
            Start recovering →
          </Link>
        </div>

        <div className="mt-12">
          <TrustStrip />
        </div>
      </div>

      <ScrollCue />
    </section>
  );
}
