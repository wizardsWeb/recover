"use client";

import Link from "next/link";
import { Menu, X } from "lucide-react";
import { useEffect, useState } from "react";

import { LANDING_SECTIONS } from "@/components/marketing/landing-sections";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils/cn";

/**
 * The floating pill that rides above the hero video.
 *
 * White in both colour modes and not themed, because it sits on a video rather
 * than on a page surface. There is no theme in which the frame behind it is
 * predictable, so the pill supplies its own ground and the whole question goes
 * away — the same reasoning that keeps the app's rail dark in both modes.
 *
 * Active state is three 3px dots under the label, drawn as one 3px square plus
 * two `box-shadow` copies of itself. A single pseudo-element cannot paint three
 * separate marks any other way without adding two more elements to every link.
 */
export function LandingNav() {
  const activeId = useScrollSpy(LANDING_SECTIONS.map((section) => section.id));
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="pointer-events-none fixed inset-x-0 top-5 z-50 flex justify-center px-4">
      <nav
        aria-label="Main"
        className="pointer-events-auto flex items-center gap-1 rounded-full bg-white py-1.5 pr-1.5 pl-2 shadow-[0_4px_14px_rgb(0_0_0/0.16)]"
      >
        <Link
          href="/"
          aria-label="Recover — home"
          className="flex size-9 shrink-0 items-center justify-center rounded-full bg-white ring-1 ring-black/10 transition-transform duration-150 hover:scale-105"
        >
          <span aria-hidden className="font-display text-sm leading-none font-bold text-gold">
            ₹R
          </span>
        </Link>

        <ul className="mx-1 hidden items-center md:flex">
          {LANDING_SECTIONS.map((section) => {
            const active = activeId === section.id;
            return (
              <li key={section.id}>
                <a
                  href={`#${section.id}`}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "relative block rounded-full px-3.5 py-1.5 text-sm font-medium text-[#2e2e2e] transition-colors duration-150 hover:text-black",
                    // The three dots. `currentColor` would make them fade with
                    // the link's own hover transition; they are a state marker,
                    // so they stay put.
                    active &&
                      "after:absolute after:bottom-0.5 after:left-1/2 after:size-[3px] after:-translate-x-1/2 after:rounded-full after:bg-black after:shadow-[-6px_0_0_black,6px_0_0_black] after:content-['']",
                  )}
                >
                  {section.label}
                </a>
              </li>
            );
          })}
        </ul>

        <Link
          href="/login"
          className="ml-1 hidden rounded-full bg-[#111] px-4 py-2 text-sm font-semibold text-white transition-colors duration-150 hover:bg-black md:block"
        >
          Sign in
        </Link>

        {/* ---- Mobile ------------------------------------------------------
            Below `md` the five labels do not fit beside the mark and the pill,
            so they move into a sheet rather than wrapping onto a second line —
            a two-line floating pill stops reading as a pill. */}
        <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
          <SheetTrigger
            render={
              <button
                type="button"
                aria-label="Open menu"
                className="flex size-9 items-center justify-center rounded-full text-[#2e2e2e] transition-colors duration-150 hover:bg-black/5 md:hidden"
              >
                <Menu className="size-5" strokeWidth={1.75} aria-hidden />
              </button>
            }
          />
          <SheetContent side="top" className="bg-ink-900 text-white">
            <SheetHeader className="flex-row items-center justify-between">
              <SheetTitle className="font-display text-white">Recover</SheetTitle>
              <SheetClose
                render={
                  <button
                    type="button"
                    aria-label="Close menu"
                    className="rounded-full p-1.5 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
                  >
                    <X className="size-5" strokeWidth={1.75} aria-hidden />
                  </button>
                }
              />
            </SheetHeader>
            <ul className="flex flex-col gap-1 px-4 pb-6">
              {LANDING_SECTIONS.map((section) => (
                <li key={section.id}>
                  <a
                    href={`#${section.id}`}
                    onClick={() => setMenuOpen(false)}
                    className="block rounded-md px-3 py-2.5 text-base text-white/80 transition-colors hover:bg-white/10 hover:text-white"
                  >
                    {section.label}
                  </a>
                </li>
              ))}
              <li className="mt-2">
                <Link
                  href="/login"
                  className="block rounded-full bg-white px-4 py-2.5 text-center text-sm font-semibold text-ink-900"
                >
                  Sign in
                </Link>
              </li>
            </ul>
          </SheetContent>
        </Sheet>
      </nav>
    </div>
  );
}

/**
 * Which of `ids` is currently the section in view.
 *
 * An `IntersectionObserver` rather than a scroll listener: the browser does the
 * geometry off the main thread, so this does not fire a layout read on every
 * frame of a scroll. The `rootMargin` shrinks the viewport to a band across its
 * middle, which is what makes "in view" mean the section the reader is looking
 * at rather than every section touching the viewport at once.
 */
function useScrollSpy(ids: readonly string[]): string | null {
  const [activeId, setActiveId] = useState<string | null>(ids[0] ?? null);
  // Serialised so the effect's dependency is a string rather than an array
  // identity, which changes on every render and would re-create the observer.
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
        // The topmost of whatever is in the band, so scrolling up and down
        // through a boundary settles on the same section either way.
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
