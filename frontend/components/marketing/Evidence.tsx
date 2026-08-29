/**
 * The four measured figures, as a ruled row.
 *
 * Set in the monospace, which is the one place on this page where that face is
 * load-bearing rather than a preference: these are the product's own output, and
 * the dashboard renders them in the same face. A reader who gets as far as
 * signing up should recognise the typography of the numbers.
 *
 * No count-up animation. A figure that animates is a figure asking to be
 * admired; these are asking to be checked, and the denominator under each one is
 * doing more work than any motion could.
 *
 * `₹` is the only coloured glyph on the entire page — see `--rupee` in
 * globals.css. It appears here and on the leak index and nowhere else, which is
 * what makes one colour in an achromatic page read as meaning rather than as
 * decoration.
 */
const FIGURES = [
  { value: "35.2", unit: "%", label: "of at-risk revenue recovered", rupee: false },
  { value: "9.2", unit: "L", label: "incremental, per 1,000 cases", rupee: true },
  { value: "0", unit: "", label: "compliance violations", rupee: false },
  { value: "91", unit: "s", label: "to detect a bank outage", rupee: false },
];

export function Evidence() {
  return (
    <section id="evidence" className="bg-paper px-5 py-24 sm:px-7 sm:py-40">
      <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-3">
        <h2 className="type-statement max-w-[20ch] text-ink">Measured, not asserted.</h2>
        <p className="type-meta max-w-[34ch]">
          One case in twenty is held out untouched. That is what makes the second figure
          incremental rather than gross.
        </p>
      </div>

      <dl className="mt-14 grid grid-cols-2 border-t border-hairline sm:mt-20 sm:grid-cols-4">
        {FIGURES.map((figure) => (
          <div
            key={figure.label}
            // A hairline between columns and under every cell. On two columns
            // the odd cells lose their right rule so the grid does not draw a
            // line down the page edge.
            className="border-b border-hairline px-0 py-8 sm:border-r sm:last:border-r-0 sm:px-6 sm:first:pl-0"
          >
            <dd className="font-mono text-[clamp(2.5rem,6vw,4.5rem)] leading-[0.9] tracking-[-0.04em] text-ink tabular-nums">
              {figure.rupee ? <span className="text-rupee">₹</span> : null}
              {figure.value}
              <span className="text-ink-faint">{figure.unit}</span>
            </dd>
            <dt className="type-meta mt-3 max-w-[18ch]">{figure.label}</dt>
          </div>
        ))}
      </dl>
    </section>
  );
}
