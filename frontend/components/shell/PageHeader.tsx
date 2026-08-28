import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  /** Buttons or filters, aligned right on the same baseline as the title. */
  actions?: ReactNode;
  /**
   * Rendered inline beside the title.
   *
   * For status that qualifies the heading itself — the live-connection dot —
   * rather than something the user acts on. Those belong in `actions`, which
   * sits at the far right of the row and would read as a control.
   */
  titleAdornment?: ReactNode;
}

export function PageHeader({ title, subtitle, actions, titleAdornment }: PageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="font-display text-2xl font-semibold tracking-[-0.02em] text-ink">
            {title}
          </h1>
          {titleAdornment}
        </div>
        {subtitle ? <p className="mt-1 text-sm text-ink-muted">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}
