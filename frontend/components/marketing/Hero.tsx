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
    <section id="index" className="relative h-dvh w-full overflow-hidden bg-ink">
      <Image
        src={PLATES.open.src}
        alt={PLATES.open.alt}
        fill
        sizes="100vw"
        priority
        className="object-cover"
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

          `mix-blend-difference`, the same technique the chrome uses, because
          this corner of the plate is bright overcast sky — white text sat on it
          at any opacity and vanished. Difference inverts it to near-black there
          and back to white if the crop ever changes, so legibility does not
          depend on which part of the photograph the viewport happens to show. */}
      <p className="absolute right-5 bottom-8 hidden max-w-[24ch] text-right text-[13px] leading-[1.3] text-white mix-blend-difference sm:block sm:right-7 sm:bottom-10">
        35.2% of at-risk revenue recovered across 1,000 simulated cases, measured against an
        untouched holdout.
      </p>
    </section>
  );
}
