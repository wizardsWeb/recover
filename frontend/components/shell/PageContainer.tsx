import type { ReactNode } from "react";

import { cn } from "@/lib/utils/cn";

export function PageContainer({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("mx-auto max-w-7xl px-8 py-6", className)}>{children}</div>;
}
