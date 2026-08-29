"use client";

import type { ReactNode } from "react";

import { AnimatedNumber, AnimatedPercent } from "@/components/ui/AnimatedNumber";
import { LiftCard } from "@/components/ui/LiftCard";
import { formatRupeeDigits } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

/** Which semantic colour the accent rule and the icon take. */
export type KpiTone = "brand" | "success" | "warning" | "danger" | "info";

const TONE_RULE: Record<KpiTone, string> = {
  brand: "border-l-brand",
  success: "border-l-success",
  warning: "border-l-warning",
  danger: "border-l-danger",
  info: "border-l-info",
};

const TONE_ICON: Record<KpiTone, string> = {
  brand: "text-brand",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
  info: "text-info",
};

export interface KpiCardProps {
  label: string;
  /** Paise for `inr`, a 0-1 rate for `percent`, a plain figure otherwise. */
  value: number;
  kind: "inr" | "count" | "percent";
  tone: KpiTone;
  /**
   * The already-rendered glyph, e.g. `icon={<Layers strokeWidth={1.5} />}`.
   *
   * A rendered element, not a component. This is a client component, and a
   * component reference is not serialisable across the boundary — a Server
   * Component passing `icon={Layers}` crashes the page with "Only plain objects
   * can be passed to Client Components", which is what the playbook detail page
   * did. A React element survives that crossing; a `forwardRef` object does not.
   */
  icon: ReactNode;
  /** Rendered under the number — a denominator, a delta, a period. */
  footnote?: string;
  /** Hold the count at zero until the card scrolls into view. */
  startOnView?: boolean;
  className?: string;
  /** Enter as part of a `StaggerList`. */
  staggered?: boolean;
}

/**
 * One KPI tile, used by every screen that shows a headline number.
 *
 * The signature is the rupee glyph: set as its own element, smaller than the
 * digits and in the brand blue, so the eye reads "money" before it reads "how
 * much". That only works while it is rare — it appears on these tiles and in
 * the landing stats and nowhere else, which is why the tables underneath use
 * plain monospaced figures.
 *
 * Colour lives on a 3px left rule and a 20px icon, not on the card's fill. Four
 * tinted cards in a row is four competing surfaces; a rule is the same
 * information at a tenth of the ink, and it leaves the number itself on the
 * card's own ground where it reads at full contrast.
 *
 * The number is `tabular-nums`. A live figure counting up in proportional
 * digits changes width on every frame, which shivers the whole card.
 */
export function KpiCard({
  label,
  value,
  kind,
  tone,
  icon,
  footnote,
  startOnView = false,
  className,
  staggered = false,
}: KpiCardProps) {
  return (
    <LiftCard staggered={staggered} className={className}>
      <div
        className={cn(
          "h-full rounded-none border border-hairline border-l-[3px] bg-elevated p-5 shadow-card",
          TONE_RULE[tone],
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <p className="text-[13px] text-ink-muted">{label}</p>
          {/* The tone colour goes on the wrapper and the glyph inherits it
              through currentColor, because an arbitrary node cannot be handed a
              className the way a component could. */}
          <span className={cn("shrink-0 [&>svg]:size-5", TONE_ICON[tone])} aria-hidden>
            {icon}
          </span>
        </div>

        <p className="mt-3 flex items-baseline gap-1 font-display font-bold tracking-[-0.03em] text-ink tabular-nums">
          {kind === "inr" && (
            // Not aria-hidden: the digits below carry no currency of their
            // own, so hiding the glyph would have a screen reader read
            // "one lakh forty-five thousand" of nothing in particular.
            <span className="text-[28px] leading-none text-brand">₹</span>
          )}
          <span className="text-[clamp(30px,3.6vw,48px)] leading-none">
            {kind === "inr" ? (
              <AnimatedNumber value={value} startOnView={startOnView} format={formatRupeeDigits} />
            ) : kind === "percent" ? (
              <AnimatedPercent value={value} startOnView={startOnView} />
            ) : (
              <AnimatedNumber value={value} startOnView={startOnView} />
            )}
          </span>
        </p>

        {footnote ? <p className="mt-2 text-xs text-ink-faint">{footnote}</p> : null}
      </div>
    </LiftCard>
  );
}
