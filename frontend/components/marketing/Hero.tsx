import { ButtonLink } from "@/components/ui/button-link";

/**
 * The recovery-rate figure is static in Phase 1. Phase 8 animates it from zero
 * with Framer Motion; the markup is shaped so only the number node changes.
 */
const RECOVERY_RATE = "35.2%";

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="mx-auto max-w-6xl px-6 pt-20 pb-16 sm:pt-28 sm:pb-24">
        <div className="grid items-center gap-16 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="max-w-2xl">
            <h1 className="font-display text-5xl leading-[1.05] font-medium tracking-[-0.03em] text-ink sm:text-6xl">
              Every rupee has a reason.
            </h1>

            <p className="mt-6 text-lg leading-relaxed text-ink-muted">
              Recover is an AI agent for Razorpay merchants that finds revenue slipping away —
              failed payments, dropped carts, broken subscriptions, overdue invoices — and wins it
              back. Compliantly. Transparently. Sharper every day.
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-3">
              <ButtonLink href="/signup" size="lg">
                Get started
              </ButtonLink>
              <ButtonLink href="#how-it-works" size="lg" variant="outline">
                See how it works
              </ButtonLink>
            </div>
          </div>

          {/* The number, given the room a number this large deserves. */}
          <figure className="lg:border-l lg:border-hairline lg:pl-16">
            <div className="tabular font-display text-7xl leading-none font-medium tracking-[-0.04em] text-brand sm:text-8xl">
              {RECOVERY_RATE}
            </div>
            <figcaption className="mt-4 max-w-[16rem] text-sm leading-relaxed text-ink-faint">
              recovery rate across 1,000 simulated cases
            </figcaption>
          </figure>
        </div>
      </div>

      {/* A single gold hairline, the way a ledger rules off a section. */}
      <div aria-hidden className="rule-gold mx-auto h-px max-w-6xl" />
    </section>
  );
}
