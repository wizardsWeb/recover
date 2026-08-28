import Image from "next/image";

import { SCENARIO_IMAGES } from "@/lib/assets/images";

/**
 * Three ways revenue slips, and what the agent does about each.
 *
 * Photographs rather than icons because these are the three *situations* a
 * merchant recognises, and an abstract glyph asks them to decode a metaphor
 * before they can tell whether the product is for them.
 *
 * The overlay is a gradient rather than a flat scrim, dark at the foot where
 * the text sits and clearing towards the top so the picture survives. That is
 * also what keeps the copy above 4.5:1 on every image without having to check
 * each one — the text never sits on anything lighter than 80% ink.
 */
const STEPS = [
  {
    number: "01",
    playbook: "checkout_abandonment" as const,
    title: "A cart is abandoned",
    body: "It reads where they stopped — method, OTP, the bank's own step — and infers whether the price, the trust, or the plumbing lost them.",
  },
  {
    number: "02",
    playbook: "subscription_failure" as const,
    title: "A mandate fails",
    body: "Three failures on the 1st with an insufficient-funds code is a salary-timing problem, not a broken instrument. It retries when the money lands.",
  },
  {
    number: "03",
    playbook: "b2b_overdue" as const,
    title: "An invoice runs late",
    body: "A business that always pays late and always pays needs a different message from one that has never been late before.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="scroll-mt-14 bg-base py-20 sm:py-24">
      <div className="mx-auto max-w-6xl px-6">
        <h2 className="font-display text-3xl leading-tight font-semibold tracking-[-0.02em] text-ink sm:text-4xl">
          Three ways revenue slips
        </h2>
        <p className="mt-3 max-w-2xl text-base leading-relaxed text-ink-muted">
          Each has a different cause and a different fix. The agent tells them apart before it
          acts.
        </p>

        <ul className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {STEPS.map((step) => {
            const image = SCENARIO_IMAGES[step.playbook];
            return (
              <li key={step.number}>
                <article className="group relative isolate flex h-80 flex-col justify-end overflow-hidden rounded-card border border-hairline transition-transform duration-200 ease-out hover:-translate-y-1">
                  <Image
                    src={image.src}
                    alt={image.alt}
                    fill
                    sizes="(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
                    className="-z-20 object-cover"
                  />
                  <div
                    aria-hidden
                    className="absolute inset-0 -z-10 bg-gradient-to-t from-ink-900 via-ink-900/80 to-ink-900/25"
                  />

                  <div className="p-6">
                    <span
                      aria-hidden
                      className="font-display text-3xl font-bold tracking-[-0.02em] text-white/45"
                    >
                      {step.number}
                    </span>
                    <h3 className="mt-1 font-display text-lg font-semibold text-white">
                      {step.title}
                    </h3>
                    <p className="mt-1.5 text-sm leading-relaxed text-ink-200">{step.body}</p>
                  </div>
                </article>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
