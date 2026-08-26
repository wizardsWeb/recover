"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { breadcrumbsFor } from "@/components/shell/nav";

export function Breadcrumbs() {
  const pathname = usePathname();
  const trail = breadcrumbsFor(pathname);

  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex items-center gap-1.5 text-sm">
        {trail.map((item, index) => {
          const last = index === trail.length - 1;
          return (
            <Fragment key={item.href}>
              {index > 0 && (
                <ChevronRight className="size-3.5 shrink-0 text-ink-faint" aria-hidden />
              )}
              <li>
                {last ? (
                  <span aria-current="page" className="font-medium text-ink">
                    {item.label}
                  </span>
                ) : (
                  <Link href={item.href} className="text-ink-muted transition-colors hover:text-ink">
                    {item.label}
                  </Link>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
