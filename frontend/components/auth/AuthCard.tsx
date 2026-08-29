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
export function AuthCard({ title, description, children, footer, className }: AuthCardProps) {
  return (
    <div className={cn("rounded-card border border-hairline bg-elevated p-8 shadow-card", className)}>
      <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">{title}</h1>
      {description ? (
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">{description}</p>
      ) : null}

      <div className="mt-6">{children}</div>

      {footer ? (
        <>
          <div className="mt-6 h-px bg-hairline" />
          <div className="mt-4 text-sm text-ink-muted">{footer}</div>
        </>
      ) : null}
    </div>
  );
}
