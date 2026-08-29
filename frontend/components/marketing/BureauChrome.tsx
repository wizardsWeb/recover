"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { LANDING_SECTIONS } from "@/components/marketing/landing-sections";
import { cn } from "@/lib/utils/cn";

/**
 * The page's only chrome: a wordmark and an index, both fixed, both 13px.
 *
 * There is no header bar. Nothing has a background, a border, or a container —
 * the two corners sit directly on whatever the page is showing, which is what
 * lets the hero photograph run to all four edges. The whole of the navigation
 * weighs less than a button would.
 *
 * `mix-blend-difference` is doing the work that a scrim or a scroll listener
 * would otherwise do. The chrome is white; over a dark photograph difference
 * leaves it white, and over the white page below it inverts to black. One
 * declaration, no measuring, and it is correct on every frame of a scroll
 * including the boundary between two sections.
 */
export function BureauChrome() {
  const activeId = useScrollSpy(LANDING_SECTIONS.map((section) => section.id));

  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-50 mix-blend-difference">
      <div className="flex items-start justify-between px-5 py-4 text-[13px] leading-[1.15] text-white sm:px-7">
        {/* Three lines, because the name alone does not say what this is and a
            tagline in a sentence would be a tagline. Name, then category. */}
        <Link href="/" className="pointer-events-auto">
          <span className="block">Recover</span>
          <span className="block">Revenue Recovery</span>
          <span className="block">for Razorpay</span>
        </Link>

        {/* Comma-separated, like an index line. The commas are rendered as
            content rather than as separators so they inherit the link colour
            and stay on the baseline. */}
        <nav aria-label="Sections" className="pointer-events-auto hidden sm:block">
          {LANDING_SECTIONS.map((section, index) => (
            <span key={section.id}>
              <a
                href={`#${section.id}`}
                aria-current={activeId === section.id ? "true" : undefined}
                className={cn(
                  "underline-offset-[0.25em] transition-opacity duration-200 hover:opacity-60",
                  activeId === section.id ? "underline" : "no-underline",
                )}
              >
                {section.label}
              </a>
              {index < LANDING_SECTIONS.length - 1 ? <span>,&nbsp;</span> : null}
            </span>
          ))}
        </nav>

        <Link href="/login" className="pointer-events-auto underline-offset-[0.25em] hover:underline sm:hidden">
          Sign in
        </Link>
      </div>
    </div>
  );
}

/**
 * Which section is in view.
 *
 * An `IntersectionObserver` rather than a scroll listener: the browser does the
 * geometry off the main thread, so this does not force a layout read on every
 * frame. The `rootMargin` shrinks the viewport to a band across its middle,
 * which is what makes "in view" mean the section being looked at rather than
 * every section currently touching the viewport.
 */
function useScrollSpy(ids: readonly string[]): string | null {
  const [activeId, setActiveId] = useState<string | null>(ids[0] ?? null);
  // Serialised so the effect depends on a string rather than on an array
  // identity, which changes every render and would rebuild the observer.
  const key = ids.join(",");

  useEffect(() => {
    const sections = key
      .split(",")
      .map((id) => document.getElementById(id))
      .filter((element): element is HTMLElement => element !== null);

    if (sections.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting);
        if (visible.length === 0) return;
        const top = visible.reduce((best, entry) =>
          entry.boundingClientRect.top < best.boundingClientRect.top ? entry : best,
        );
        setActiveId(top.target.id);
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );

    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, [key]);

  return activeId;
}
