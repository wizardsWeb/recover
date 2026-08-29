import type { ReactNode } from "react";

import { cn } from "@/lib/utils/cn";

interface AuthCardProps {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}

/**
 * The frame shared by sign-in, sign-up, and onboarding — one card, one rule,
 * one footer line. Keeping it in a single place is what stops the three pages
 * from drifting apart a pixel at a time.
 */
/**
 * The frame shared by sign-in, sign-up and onboarding.
 *
 * The fields do not animate in. They used to cascade at 60ms intervals, which
 * looked pleasant and meant that until the animation finished the form had
 * invisible fields — and anything that delays requestAnimationFrame (a restored
 * background tab, a low-end device, a long task elsewhere on the page) leaves a
 * sign-up form that appears broken. That is a bad trade for a 200ms flourish on
 * the one screen where a confused reader simply leaves.
 *
 * No longer a card. A bordered panel floating on a white page was the one
 * container left in the product, and in a system built on hairlines a box around
 * a form is a box around nothing — the column already bounds it. What remains is
 * a title, a line of meta, the fields, and a rule above the footer link.
 */
export function AuthCard({ title, description, children, footer, className }: AuthCardProps) {
  return (
    <div className={cn(className)}>
      <h1 className="text-[clamp(2rem,4vw,2.75rem)] leading-[0.95] tracking-[-0.035em] text-ink">
        {title}
      </h1>
      {description ? <p className="type-meta mt-3 max-w-[34ch]">{description}</p> : null}

      <div className="mt-10">{children}</div>

      {footer ? (
        <div className="mt-10 border-t border-hairline pt-4 text-[13px] text-ink-muted">
          {footer}
        </div>
      ) : null}
    </div>
  );
}
