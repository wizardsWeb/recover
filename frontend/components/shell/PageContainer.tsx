import type { ReactNode } from "react";

import { PageTransition } from "@/components/shell/PageTransition";
import { cn } from "@/lib/utils/cn";

/**
 * The page's gutter, and its entrance.
 *
 * The transition wraps the children rather than the container so the padding is
 * not part of what animates — a `y` on the outer element would slide the gutter
 * too, which reads as the whole layout shifting rather than as content arriving.
 */
export function PageContainer({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mx-auto max-w-7xl px-8 py-6", className)}>
      <PageTransition>{children}</PageTransition>
    </div>
  );
}
