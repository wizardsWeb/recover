import Link from "next/link";

import { cn } from "@/lib/utils/cn";

interface WordmarkProps {
  className?: string;
  /** Rendered as a link to `/` unless false. */
  href?: string | false;
  size?: "sm" | "md" | "lg";
  /** Recolours the ledger rule — it sits on dark chrome as well as on paper. */
  lineClassName?: string;
}

const SIZES = {
  sm: "text-base",
  md: "text-lg",
  lg: "text-2xl",
} as const;

/**
 * The Recover wordmark: the name in General Sans with a single gold rule under
 * the last letter — a ledger line, drawn once.
 */
export function Wordmark({ className, href = "/", size = "md", lineClassName }: WordmarkProps) {
  const mark = (
    <span
      className={cn(
        "relative inline-block font-display font-semibold tracking-[-0.03em] text-ink",
        SIZES[size],
        className,
      )}
    >
      Recover
      <span
        aria-hidden
        className={cn("absolute -bottom-0.5 left-0 h-px w-full bg-brand-line opacity-70", lineClassName)}
      />
    </span>
  );

  if (href === false) return mark;
  return (
    <Link href={href} className="rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {mark}
    </Link>
  );
}
