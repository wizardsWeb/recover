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
 * The floating nav pill.
 *
 * A deliberate exception to the rest of the system, and it opts out of three
 * rules explicitly rather than by accident:
 *
 *   * **Radius.** Every radius token is 0, so `rounded-full` and `rounded-lg`
 *     are both square here. The pill uses an arbitrary `rounded-[999px]`, which
 *     bypasses the theme entirely.
 *   * **Shadow.** Every shadow token is `none`. The lift under the pill is an
 *     arbitrary value for the same reason.
 *   * **Weight.** Every weight utility resolves to 400. `font-nav` is the one
 *     escape, and it exists because 15px white on near-black reads thinner than
 *     the same size of ink on paper.
 *
 * Those three exceptions are what make it a floating object rather than a band,
 * and they are why it needs no scroll listener and no colour switching: it
 * carries its own dark ground, so it is legible over a photograph, over white
 * paper, and over the boundary between them. The version before this switched
 * white-to-ink on scroll and was invisible twice — once over mid-grey concrete,
 * once over the white sections.
 *
 * The circular mark is the only place `₹` appears in the chrome, in the one
 * colour the product allows, on white. Everything else in the pill is white on
 * near-black.
 */
export function BureauChrome() {
  const activeId = useScrollSpy(LANDING_SECTIONS.map((section) => section.id));
  const [menuOpen, setMenuOpen] = useState(false);

  // `Start` is the page's own call to action and is reachable from the Sign up
  // button beside it, so it is not repeated as a link.
  const links = LANDING_SECTIONS.filter((section) => section.id !== "start");

  return (
    <div className="pointer-events-none fixed inset-x-0 top-4 z-50 flex justify-center px-4 sm:top-6">
      <nav
        aria-label="Main"
        className="pointer-events-auto flex items-center gap-1 rounded-[999px] bg-[#0d0d0d] p-1.5 shadow-[0_10px_34px_rgb(0_0_0/0.22)] sm:gap-2"
      >
        {/* The mark. A circle inside a pill, which is the shape the reference
            uses — and the only round object left in the product. */}
        <Link
          href="/"
          aria-label="Recover — home"
          className="flex size-10 shrink-0 items-center justify-center rounded-[999px] bg-white transition-transform duration-200 hover:scale-105 focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:outline-none"
        >
          <span aria-hidden className="font-nav text-[17px] leading-none text-rupee">
            ₹
          </span>
        </Link>

        <ul className="hidden items-center md:flex">
          {links.map((section) => {
            const active = activeId === section.id;
            return (
              <li key={section.id}>
                <a
                  href={`#${section.id}`}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "block rounded-[999px] px-4 py-2 font-nav text-[15px] transition-colors duration-200 focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:outline-none",
                    // Active is a fill rather than an underline. Inside a filled
                    // pill an underline reads as a link that has been visited;
                    // a lighter well reads as "you are here".
                    active ? "bg-white/[0.14] text-white" : "text-white/65 hover:text-white",
                  )}
                >
                  {section.label}
                </a>
              </li>
            );
          })}
        </ul>

        <div className="ml-1 flex items-center gap-1 sm:gap-2">
          <Link
            href="/login"
            className="rounded-[999px] px-3 py-2 font-nav text-[15px] whitespace-nowrap text-white/65 transition-colors duration-200 hover:text-white focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:outline-none sm:px-4"
          >
            Log in
          </Link>

          {/* The one filled affordance on the page. It is white on near-black
              inside a dark pill on a white page — three inversions deep, which
              is what makes it the loudest thing in the chrome without being
              large. */}
          <Link
            href="/signup"
            className="rounded-[999px] bg-white px-4 py-2 font-nav text-[15px] whitespace-nowrap text-[#0d0d0d] transition-colors duration-200 hover:bg-white/85 focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:outline-none sm:px-5"
          >
            Sign up
          </Link>
        </div>

        {/* ---- Mobile ------------------------------------------------------
            Below `md` the four labels do not fit beside the mark and two
            buttons, so they move into a sheet. A pill that wraps to two lines
            stops being a pill. */}
        <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
          <SheetTrigger
            render={
              <button
                type="button"
                aria-label="Open menu"
                className="flex size-10 shrink-0 items-center justify-center rounded-[999px] text-white/70 transition-colors duration-200 hover:bg-white/10 hover:text-white focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:outline-none md:hidden"
              >
                <Menu className="size-5" strokeWidth={1.75} aria-hidden />
              </button>
            }
          />
          <SheetContent side="top" className="border-0 bg-[#0d0d0d] text-white">
            <SheetHeader className="flex-row items-center justify-between">
              <SheetTitle className="font-nav text-white">Recover</SheetTitle>
              <SheetClose
                render={
                  <button
                    type="button"
                    aria-label="Close menu"
                    className="rounded-[999px] p-2 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
                  >
                    <X className="size-5" strokeWidth={1.75} aria-hidden />
                  </button>
                }
              />
            </SheetHeader>
            <ul className="flex flex-col gap-1 px-4 pb-6">
              {links.map((section) => (
                <li key={section.id}>
                  <a
                    href={`#${section.id}`}
                    onClick={() => setMenuOpen(false)}
                    className="block rounded-[999px] px-4 py-3 font-nav text-base text-white/75 transition-colors hover:bg-white/10 hover:text-white"
                  >
                    {section.label}
                  </a>
                </li>
              ))}
            </ul>
          </SheetContent>
        </Sheet>
      </nav>
    </div>
  );
}

/**
 * Which section is in view.
 *
 * An `IntersectionObserver` rather than a scroll listener: the browser does the
 * geometry off the main thread, so this does not force a layout read per frame.
 * The `rootMargin` shrinks the viewport to a band across its middle, which makes
 * "in view" mean the section being looked at rather than every section currently
 * touching the viewport.
 */
function useScrollSpy(ids: readonly string[]): string | null {
  const [activeId, setActiveId] = useState<string | null>(ids[0] ?? null);
  // Serialised so the effect depends on a string rather than an array identity,
  // which changes every render and would rebuild the observer.
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
