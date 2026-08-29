/**
 * The one paragraph on the page set in the serif, at display size.
 *
 * This is the counterpoint the whole type system exists for. Everything else is
 * the grotesque; this is the same page speaking in a different register, and it
 * carries the argument rather than a feature. Instrument Serif has a single
 * weight and high stroke contrast, which at 96px reads as a printed statement
 * rather than as a headline.
 *
 * Leading is 0.92 — under the type size — so the three lines close into a
 * paragraph-shaped block. It runs to the page edges with the same 20px gutter as
 * everything else, because a measure this large does not need a container to be
 * readable; the line breaks are doing that work.
 */
export function SerifStatement() {
  return (
    <section className="bg-paper px-5 py-24 sm:px-7 sm:py-40">
      <p className="type-statement max-w-[26ch] font-serif text-ink sm:max-w-none">
        Recovery is a claim about cause. Every one this agent makes is written
        down, and every one can be checked.
      </p>

      <p className="type-meta mt-10 max-w-[52ch] sm:mt-14">
        The alternative is a dunning cron: retry three times, message everyone the same way, and
        count whatever arrives afterwards. That number cannot tell you what it caused.
      </p>
    </section>
  );
}
