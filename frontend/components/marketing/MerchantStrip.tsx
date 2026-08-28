import { BookOpen, Boxes, Sparkles } from "lucide-react";

/**
 * The three fictional merchants the scenarios are written around.
 *
 * Drawn in `--ink-400` rather than in brand colour, and deliberately not
 * "logos": these are personas from `scenarios.md`, not customers, and rendering
 * them as a bright logo wall would be claiming a customer base that does not
 * exist. Subdued is both the honest treatment and, as it happens, how a real
 * logo strip looks.
 */
const MERCHANTS = [
  { name: "Kajal & Co.", trade: "D2C beauty", icon: Sparkles },
  { name: "Zenith Learning", trade: "Edtech subscriptions", icon: BookOpen },
  { name: "Sharma Distributors", trade: "B2B distribution", icon: Boxes },
];

export function MerchantStrip() {
  return (
    <section className="border-y border-hairline bg-elevated py-12">
      <div className="mx-auto max-w-6xl px-6">
        <p className="text-center text-[11px] font-medium tracking-[0.12em] text-ink-faint uppercase">
          The merchants these scenarios are written around
        </p>
        <ul className="mt-7 flex flex-wrap items-center justify-center gap-x-12 gap-y-6">
          {MERCHANTS.map(({ name, trade, icon: Icon }) => (
            <li key={name} className="flex items-center gap-2.5 text-ink-400">
              <Icon className="size-5 shrink-0" strokeWidth={1.5} aria-hidden />
              <span>
                <span className="block font-display text-sm font-semibold tracking-[-0.01em]">
                  {name}
                </span>
                <span className="block text-[11px]">{trade}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
