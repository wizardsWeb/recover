import { CaseDetailPreview } from "@/components/marketing/CaseDetailPreview";
import { ButtonLink } from "@/components/ui/button-link";

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="mx-auto max-w-6xl px-6 pt-20 pb-16 sm:pt-28 sm:pb-24">
        <div className="grid items-center gap-14 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="max-w-2xl">
            <h1 className="font-display text-5xl leading-[1.05] font-medium tracking-[-0.03em] text-ink sm:text-6xl">
              Every rupee has a reason.
            </h1>

            {/* The ledger rule, directly under the line it underwrites. */}
            <div aria-hidden className="rule-gold mt-7 h-px w-40" />

            <p className="mt-7 text-xl leading-relaxed text-ink-muted">
              Recover watches your Razorpay event stream in real time. When revenue slips — failed
              payments, dropped carts, broken mandates, overdue invoices — it finds it, diagnoses
              it, and wins it back.
            </p>

            <div className="mt-9 flex flex-wrap items-center gap-3">
              <ButtonLink href="/signup" size="lg">
                Start recovering →
              </ButtonLink>
              <ButtonLink href="#how-it-works" size="lg" variant="ghost">
                See how it works
              </ButtonLink>
            </div>
          </div>

          {/* Not a screenshot — the same markup vocabulary as the real case
              detail page, so it re-themes with the site and cannot go stale. */}
          <div className="flex justify-center lg:justify-end">
            <CaseDetailPreview />
          </div>
        </div>
      </div>
    </section>
  );
}
