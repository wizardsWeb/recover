"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fragment } from "react";

import { breadcrumbsFor } from "@/components/shell/nav";

export function Breadcrumbs() {
  const pathname = usePathname();
  const trail = breadcrumbsFor(pathname);

  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex items-center gap-2 text-sm text-ink-muted">
        {trail.map((item, index) => {
          const last = index === trail.length - 1;
          return (
            <Fragment key={item.href}>
              {index > 0 && (
                <span className="shrink-0 text-ink-faint" aria-hidden>
                  /
                </span>
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
