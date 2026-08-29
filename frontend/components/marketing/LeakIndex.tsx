/**
 * The four leaks, as an index.
 *
 * A ruled list rather than four cards, and the difference matters: cards make
 * the four things look like a product's feature set, where a numbered index
 * with a rule between each row makes them look like a catalogue of a problem —
 * which is what they are. The rows are the page's densest moment and its only
 * repeating structure.
 *
 * The numbering earns its place here. These are the four playbooks, they are
 * numbered in the codebase, and a merchant reading the case list will see the
 * same four names in the same order — so 01–04 is an identifier, not decoration.
 *
 * Amounts are right-aligned in the monospace and are the only figures on the
 * page. They are market-wide daily estimates and the row says so, because a
 * number a reader will assume is theirs has borrowed credibility it cannot
 * repay.
 */
const LEAKS = [
  {
    number: "01",
    title: "Payments that fail",
    amount: "₹4.2L",
    body: "A declined card, a timed-out OTP, a bank that was down for ninety seconds.",
    rail: "Payment Gateway",
  },
  {
    number: "02",
    title: "Carts left at checkout",
    amount: "₹6.8L",
    body: "The intent was there. Something between the button and the bank took it away.",
    rail: "Payment Links",
  },
  {
    number: "03",
    title: "Mandates that stop",
    amount: "₹3.1L",
    body: "Three failures on the 1st is a salary-cycle problem, not a churned customer.",
    rail: "Subscriptions",
  },
  {
    number: "04",
    title: "Invoices that run late",
    amount: "₹9.4L",
    body: "A buyer who always pays late and always pays needs a different message.",
    rail: "RazorpayX",
  },
];

export function LeakIndex() {
  return (
    <section id="leaks" className="bg-paper px-5 py-24 sm:px-7 sm:py-40">
      <div className="flex items-baseline justify-between gap-6">
        <h2 className="type-statement max-w-[16ch] text-ink">Revenue doesn&rsquo;t vanish.</h2>
        <p className="type-meta hidden text-right sm:block">
          Estimated market-wide,
          <br />
          per day
        </p>
      </div>

      {/* A rule above the first row and below each one, so the list reads as a
          table without being one. `border-t` on the container plus `border-b`
          per row avoids the doubled hairline a naive `divide-y` gives at the
          boundary. */}
      <ol className="mt-14 border-t border-hairline sm:mt-20">
        {LEAKS.map((leak) => (
          <li
            key={leak.number}
            className="group grid grid-cols-[2.5rem_1fr] items-baseline gap-x-4 gap-y-2 border-b border-hairline py-6 sm:grid-cols-[4rem_minmax(0,1fr)_minmax(0,20rem)_8rem] sm:gap-x-8 sm:py-8"
          >
            <span className="type-meta text-ink-faint">{leak.number}</span>

            <h3 className="text-[clamp(1.5rem,3vw,2.5rem)] leading-[1.02] tracking-[-0.03em] text-ink">
              {leak.title}
            </h3>

            <p className="col-start-2 text-[13px] leading-[1.35] text-ink-muted sm:col-start-3">
              {leak.body}
            </p>

            <p className="col-start-2 text-[13px] text-ink-muted sm:col-start-4 sm:text-right">
              <span className="font-mono text-ink tabular-nums">{leak.amount}</span>
              <span className="mt-0.5 block text-ink-faint">{leak.rail}</span>
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
