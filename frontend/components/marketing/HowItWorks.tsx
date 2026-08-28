import { Eye, GitBranch, ShieldCheck } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface Step {
  icon: LucideIcon;
  title: string;
  body: string;
}

const STEPS: Step[] = [
  {
    icon: Eye,
    title: "Detects",
    body: "Watches every Razorpay webhook: failed payments, dropped carts, broken mandates, overdue invoices.",
  },
  {
    icon: GitBranch,
    title: "Decides",
    body: "A contextual bandit learns what works for each customer, bank, and time of day — and gets sharper with every case.",
  },
  {
    icon: ShieldCheck,
    title: "Recovers — compliantly",
    body: "Executes through Razorpay rails. Honors every opt-out. Every decision is logged and traceable.",
  },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="mx-auto max-w-6xl scroll-mt-20 px-6 py-20 sm:py-24">
      <h2 className="font-display text-sm font-semibold tracking-[0.14em] text-ink-faint uppercase">
        How it works
      </h2>

      <div className="mt-10 grid gap-px overflow-hidden rounded-lg border border-hairline bg-hairline sm:grid-cols-3">
        {STEPS.map(({ icon: Icon, title, body }, index) => (
          <div key={title} className="bg-elevated p-8">
            <div className="flex items-center gap-3">
              {/* The number is the ornament that carries the sequence; the icon
                  carries the meaning. Gold is reserved for the former. */}
              <span
                aria-hidden
                className="flex size-7 shrink-0 items-center justify-center rounded-full border border-brand-line font-display text-xs font-semibold text-brand"
              >
                {index + 1}
              </span>
              <Icon className="size-6 text-ink-muted" strokeWidth={1.5} aria-hidden />
            </div>

            <h3 className="mt-5 font-display text-xl font-semibold tracking-[-0.02em] text-ink">
              {title}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
