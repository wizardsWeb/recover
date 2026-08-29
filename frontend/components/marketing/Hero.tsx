import Image from "next/image";

import { PLATES } from "@/lib/assets/images";

/**
 * The opening plate, with the thesis set over it.
 *
 * Full viewport, one photograph, one sentence, and nothing else — no button, no
 * statistics, no scroll cue. Everything that would normally crowd a hero is
 * further down the page where it can be read properly; what is left is the only
 * claim the product actually makes.
 *
 * The headline sits at the bottom-left and is allowed to run wider than the
 * text column, because at this size the line break is the composition. It is
 * set in the grotesque at 400 with leading of 0.82 — under the type size, so
 * the two lines lock together into a block rather than reading as two lines.
 *
 * There is no scrim. The plate was chosen for its flat overcast sky, and white
 * type at this weight holds against it; darkening the whole photograph to
 * protect a headline that does not need protecting is how a page loses the
 * image it paid for. `drop-shadow` does the small amount of work required
 * instead, and only under the glyphs themselves.
 */
export function Hero() {
  return (
    <section
      id="index"
      data-chrome="over-media"
      className="relative h-dvh w-full overflow-hidden bg-ink"
    >
      <Image
        src={PLATES.open.src}
        alt={PLATES.open.alt}
        fill
        sizes="100vw"
        priority
        className="object-cover"
      />

      {/* 160px of gradient under the chrome. Every full-bleed medium on this
          page carries the same one — see `Plate` — because the chrome turns
          white whenever one is under it, and the top-right corner of this
          photograph is bright overcast sky where 13px white text is
          unreadable. */}
      <div
        aria-hidden
        className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-black/45 to-transparent"
      />

      <div className="absolute inset-x-0 bottom-0 px-5 pb-8 sm:px-7 sm:pb-10">
        <h1 className="type-colossal max-w-[22ch] text-white [text-shadow:0_1px_40px_rgb(0_0_0/0.25)]">
          Every rupee
          <br />
          has a reason.
        </h1>
      </div>

      {/* Bottom-right, in the gutter: the one number worth putting on a plate,
          and the denominator that makes it a measurement rather than a boast.

          Ink, not white, because this corner of the photograph is bright
          overcast sky while the headline's corner is dark concrete. Two text
          colours on one plate is not an inconsistency — it is the page reading
          its own image, and it is the only way both corners clear a contrast
          floor without a second scrim. The white halo is insurance for the
          narrower crops where `object-cover` slides some concrete under it. */}
      <p className="absolute right-5 bottom-8 hidden max-w-[24ch] text-right text-[13px] leading-[1.3] text-ink [text-shadow:0_0_14px_rgb(255_255_255/0.7)] sm:block sm:right-7 sm:bottom-10">
        35.2% of at-risk revenue recovered across 1,000 simulated cases, measured against an
        untouched holdout.
      </p>

    </section>
  );
}
