import Link from "next/link";

import { IMAGE_CREDITS } from "@/lib/assets/images";

/**
 * The footer, inverted.
 *
 * The reference flips its own footer to black and hangs a colossal monogram
 * across the full width, and the move is worth taking: after a long white page
 * the inversion is the only structural surprise, and it arrives exactly where
 * the reading is over.
 *
 * `RCVR` is the wordmark with its vowels removed, which is the same
 * construction the reference uses on `KNKO`. It is set to fill the width by
 * measure rather than by a font size — `10.5vw` with the tracking closed to
 * -0.06em — so it stays edge-to-edge from a phone to a large display without a
 * breakpoint.
 *
 * The ₹ before it is the one coloured glyph down here, matching the one on the
 * evidence row. Two appearances on the page, both on money.
 */
const COLUMNS = [
  {
    heading: "Product",
    links: [
      { label: "Leaks", href: "#leaks" },
      { label: "Method", href: "#method" },
      { label: "Evidence", href: "#evidence" },
    ],
  },
  {
    heading: "Account",
    links: [
      { label: "Sign in", href: "/login" },
      { label: "Open an account", href: "/signup" },
    ],
  },
  {
    heading: "Source",
    links: [
      { label: "GitHub", href: "https://github.com/wizardsWeb/razorpay_buildathon" },
      {
        label: "Submission",
        href: "https://github.com/wizardsWeb/razorpay_buildathon/blob/main/docs/submission-narrative.md",
      },
    ],
  },
];

export function BureauFooter() {
  return (
    // `dark` rather than hand-picked colours: every token inside flips to the
    // inverted palette in one move, so the links, rules and muted text are the
    // same relationships as the rest of the page rather than a second set of
    // values to keep in agreement.
    <footer className="dark bg-base text-ink">
      <div className="grid gap-10 px-5 pt-20 pb-16 sm:grid-cols-12 sm:px-7 sm:pt-28">
        <div className="text-[13px] leading-[1.15] sm:col-span-3">
          <span className="block">Recover</span>
          <span className="block text-ink-muted">Revenue Recovery</span>
          <span className="block text-ink-muted">for Razorpay</span>
        </div>

        {COLUMNS.map((column) => (
          <nav key={column.heading} className="sm:col-span-2" aria-label={column.heading}>
            <p className="type-meta text-ink-faint">{column.heading}</p>
            <ul className="mt-3 space-y-1 text-[13px]">
              {column.links.map((link) => (
                <li key={link.label}>
                  <Link href={link.href} className="text-ink-muted transition-colors hover:text-ink">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}

        <div className="sm:col-span-3">
          <p className="type-meta text-ink-faint">Built for</p>
          <p className="mt-3 text-[13px] leading-[1.35] text-ink-muted">
            Razorpay Buildathon 2026
            <br />
            Track 03 — Agentic revenue recovery
            <br />
            wizardsWeb
          </p>
        </div>
      </div>

      {/* The monogram, sized to the measure rather than to a scale.
          Five glyphs at roughly 0.62em of advance each means ~30vw of font size
          fills the viewport width, and `leading-[0.72]` crops the generous
          ascent Inter Tight leaves above the caps so the letterforms sit tight
          against the meta row instead of floating in their own box. It is a vw
          unit rather than a breakpoint ladder because the relationship being
          held is to the width, not to a device. */}
      <div className="overflow-hidden px-5 sm:px-7">
        <p
          aria-hidden
          className="text-[34vw] leading-[0.72] tracking-[-0.055em] whitespace-nowrap text-ink"
        >
          <span className="text-rupee">₹</span>RCVR
        </p>
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2 px-5 pt-6 pb-6 text-[13px] text-ink-faint sm:px-7">
        <p>All rights reserved © 2026</p>
        {/* Attribution is not required by the Pexels licence. It is here because
            a product that quietly uses someone's work as set dressing has
            decided credit is optional. */}
        <p className="flex flex-wrap gap-x-2">
          <span>Photography</span>
          {IMAGE_CREDITS.map((credit) => (
            <a key={credit.name} href={credit.url} className="transition-colors hover:text-ink">
              {credit.name}
            </a>
          ))}
          <span>on Pexels</span>
        </p>
      </div>
    </footer>
  );
}
