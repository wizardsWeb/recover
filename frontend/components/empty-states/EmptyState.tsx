import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  body: string;
  /** A link or button. Omitted when there is nothing useful to offer. */
  action?: ReactNode;
  /** Tighter padding, for an empty section inside a page rather than a whole page. */
  compact?: boolean;
  /** Overrides the icon tint — a healthy state reads green, not brand gold. */
  iconClassName?: string;
}

/**
 * The shared shell for "there is nothing here yet".
 *
 * Follows the shape `FirstTimeDashboard` and `ComingSoon` already established:
 * an elevated card holding an inset panel, a large thin icon, a display
 * heading, and one sentence explaining what would put content here.
 *
 * The icon is a stroked Lucide glyph rather than a downloaded illustration.
 * Line art at `strokeWidth={1}` inherits the design token it is tinted with, so
 * it recolours correctly in dark mode for free, ships nothing over the network,
 * and cannot fail to load during a demo.
 */
export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
  compact = false,
  iconClassName = "text-brand",
}: EmptyStateProps) {
  return (
    <div className="rounded-lg border border-hairline bg-elevated p-2">
      <div
        className={`flex flex-col items-center rounded-md bg-subtle px-8 text-center ${
          compact ? "py-12" : "py-20"
        }`}
      >
        <Icon
          className={`${compact ? "size-14" : "size-24"} ${iconClassName}`}
          strokeWidth={1}
          aria-hidden
        />
        <h2
          className={`font-display font-semibold tracking-[-0.02em] text-ink ${
            compact ? "mt-5 text-base" : "mt-8 text-xl"
          }`}
        >
          {title}
        </h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-ink-muted">{body}</p>
        {action ? <div className="mt-8">{action}</div> : null}
      </div>
    </div>
  );
}
