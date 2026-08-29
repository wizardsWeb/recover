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
 * lets the hero photograph run to all four edges.
 *
 * **Why this is not `mix-blend-difference`.** That was the first attempt and it
 * is a trap. Difference blending is excellent against black or white and useless
 * against mid-grey: white over #808080 returns #7f7f7f, which is the backdrop.
 * The hero is a grey facade under an overcast sky — both mid-tones — so the
 * wordmark ghosted over the concrete and the index washed out over the cloud.
 * It measured as present and visible in the DOM while being unreadable on
 * screen, which is the worst kind of wrong.
 *
 * So the chrome switches colour instead: white while a full-bleed photograph is
 * under it, ink over the white sections. Two states, each with real contrast,
 * decided by measurement rather than by a blend mode guessing. Every medium
 * carries a shallow top gradient so the white state holds even where the
 * photograph is bright.
 */
export function BureauChrome() {
  const activeId = useScrollSpy(LANDING_SECTIONS.map((section) => section.id));
  const overMedia = useOverMedia();

  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-50">
      <div
        className={cn(
          "flex items-start justify-between px-5 py-4 text-[13px] leading-[1.15] sm:px-7",
          // No transition. The boundary this switches on is a hard edge — the
          // hero photograph ends and white page begins — so a 300ms fade spends
          // that time passing the text through the mid-greys that are
          // unreadable against both. It also removes any state where the
          // rendered colour disagrees with the class, which is what a paused
          // transition in a throttled tab leaves behind.
          overMedia ? "text-white" : "text-ink",
        )}
      >
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


/**
 * Whether a full-bleed photograph is currently under the chrome.
 *
 * This started as "is the hero under the chrome", which was too narrow by
 * exactly three sections: the page alternates type and plate, so ink chrome sat
 * over a photograph every time a plate scrolled under it. The question is not
 * which section is first, it is what is behind these two corners right now.
 *
 * Every full-bleed medium tags itself `data-chrome="over-media"`, so this works
 * regardless of how many plates there are or what order the page puts them in —
 * adding a section cannot silently break the chrome.
 *
 * Offsets are measured once and on resize rather than per frame: reading
 * `getBoundingClientRect` forces layout, and doing that on every scroll event is
 * the one thing here that would be expensive. `scrollY` is free.
 *
 * The handler sets state directly rather than coalescing through
 * `requestAnimationFrame`. That was the first version and it was wrong twice
 * over: rAF does not fire in a background tab, so the chrome kept whatever
 * colour it had when the tab was hidden and was wrong on return — and it made
 * the behaviour impossible to assert, because the state only advanced on a
 * painted frame. Reading a cached number and calling `setState` with an
 * unchanged value is a no-op React bails out of, so the coalescing bought
 * nothing it did not also break.
 */
function useOverMedia(): boolean {
  const [overMedia, setOverMedia] = useState(true);

  useEffect(() => {
    /** The band the wordmark and index actually occupy, plus a little slack. */
    const CHROME_BAND = 80;
    let bands: Array<[number, number]> = [];

    const measure = () => {
      bands = [...document.querySelectorAll<HTMLElement>('[data-chrome="over-media"]')].map(
        (element) => {
          const top = element.getBoundingClientRect().top + window.scrollY;
          return [top, top + element.offsetHeight] as [number, number];
        },
      );
    };

    const read = () => {
      const y = window.scrollY;
      // The chrome is over a medium when that medium covers any part of the
      // band. Both comparisons are needed: `top < y + BAND` alone would stay
      // true for every medium already scrolled past.
      setOverMedia(bands.some(([top, bottom]) => top < y + CHROME_BAND && bottom > y));
    };

    const onResize = () => {
      measure();
      read();
    };

    measure();
    read();
    window.addEventListener("scroll", read, { passive: true });
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("scroll", read);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return overMedia;
}
