"use client";

import Image from "next/image";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

import { SCENARIO_IMAGES } from "@/lib/assets/images";

/** How long each scene holds, in ms. Slow on purpose — see below. */
const HOLD_MS = 7000;

/**
 * The three scenarios, each with the sentence its persona would say.
 *
 * These are personas from `scenarios.md`, not customers, and the panel labels
 * them as such. A sign-in page is exactly where a fabricated testimonial would
 * be most effective and least defensible; naming them as scenarios keeps the
 * copy doing its real job — telling a new merchant what this product is for —
 * without pretending someone said it.
 */
const SCENES = [
  {
    key: "subscription_failure",
    quote:
      "Three mandate failures on the 1st, every month, from customers who always pay by the 8th. We were writing them off as churn.",
    persona: "Zenith Learning",
    trade: "Edtech subscriptions · scenario persona",
  },
  {
    key: "checkout_abandonment",
    quote:
      "Half our drop-offs happen at the bank's OTP screen. Nobody on my team could tell me which half was price and which was plumbing.",
    persona: "Kajal & Co.",
    trade: "D2C beauty · scenario persona",
  },
  {
    key: "b2b_overdue",
    quote:
      "My best buyer is ninety days late on every invoice and has never missed one. Chasing him like a defaulter would cost me the account.",
    persona: "Sharma Distributors",
    trade: "B2B distribution · scenario persona",
  },
] as const;

/**
 * The right half of the auth pages: a slow crossfade with a quote over it.
 *
 * Seven seconds a scene, which is deliberately longer than anyone will spend
 * signing in. The panel is not a carousel asking to be watched — it is meant to
 * have changed once if you paused, and to have been a still image if you did
 * not. Anything faster turns a login form into something with motion competing
 * for the eye that should be on the password field.
 *
 * Under `prefers-reduced-motion` it holds the first scene and never advances:
 * the copy is illustrative, so losing two thirds of it costs nothing, and a
 * crossfade is exactly the kind of ambient movement that setting is about.
 */
export function AuthPanel() {
  const prefersReducedMotion = useReducedMotion();
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (prefersReducedMotion) return;
    const timer = setInterval(() => setIndex((current) => (current + 1) % SCENES.length), HOLD_MS);
    return () => clearInterval(timer);
  }, [prefersReducedMotion]);

  const scene = SCENES[index];
  const image = SCENARIO_IMAGES[scene.key];

  return (
    <div className="relative isolate hidden overflow-hidden bg-ink-900 lg:block">
      <AnimatePresence initial={false}>
        <motion.div
          key={scene.key}
          className="absolute inset-0"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={prefersReducedMotion ? { duration: 0 } : { duration: 1.4, ease: "easeInOut" }}
        >
          <Image
            src={image.src}
            alt=""
            fill
            sizes="50vw"
            className="object-cover"
            // The panel is the first thing painted on the right half of the
            // viewport, so the first scene is not lazy. The other two arrive
            // seven seconds later, which is a lifetime for an image request.
            priority={index === 0}
          />
        </motion.div>
      </AnimatePresence>

      {/* Dark at the foot where the quote sits, clearing towards the top so the
          photograph survives. It is also what keeps the copy above 4.5:1 on
          every one of the three images without having to check each.

          The mid stop is pulled down to 30% rather than the default 50%: at the
          midpoint the scrim is still 55% opaque by the time it reaches the
          quote, which left the bottom third of every photograph as a solid
          black band. The copy sits between 55% and 100% opacity, which is where
          the contrast floor is met — everything above it is now picture. */}
      <div
        aria-hidden
        className="absolute inset-0 bg-gradient-to-t from-ink-900 via-ink-900/55 via-30% to-ink-900/10"
      />

      <div className="relative flex h-full flex-col justify-end p-12">
        <p className="text-[11px] font-medium tracking-[0.15em] text-sidebar-gold uppercase">
          Built around three real leaks
        </p>

        <AnimatePresence mode="wait">
          <motion.blockquote
            key={scene.key}
            initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
            animate={prefersReducedMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={prefersReducedMotion ? { duration: 0 } : { duration: 0.5, delay: 0.2 }}
            className="mt-5 max-w-md"
          >
            <p className="font-display text-xl leading-snug font-medium tracking-[-0.01em] text-white">
              &ldquo;{scene.quote}&rdquo;
            </p>
            <footer className="mt-4 text-sm text-white/60">
              <span className="block font-medium text-white/85">{scene.persona}</span>
              {scene.trade}
            </footer>
          </motion.blockquote>
        </AnimatePresence>

        {/* Which scene, and a way to jump. Three dots rather than arrows: the
            panel is ambient, and a control pair beside a login form implies
            there is something here you are expected to read. */}
        <div className="mt-8 flex gap-1.5">
          {SCENES.map((item, position) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setIndex(position)}
              aria-label={`Show ${item.persona}`}
              aria-current={position === index}
              className={
                position === index
                  ? "h-1 w-8 rounded-none bg-white/80 transition-all"
                  : "h-1 w-4 rounded-none bg-white/25 transition-all hover:bg-white/50"
              }
            />
          ))}
        </div>
      </div>
    </div>
  );
}
