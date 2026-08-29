/**
 * Three beats, as three ruled rows.
 *
 * Numbered for the same reason the leak index is: this is a genuine sequence —
 * the agent cannot decide before it has diagnosed — so the order carries
 * information a reader needs. Where a sequence is real, numbering it is honest;
 * elsewhere on this page there are no numbers.
 *
 * No icons. An eye, a chip and a shield would each ask the reader to decode a
 * metaphor before reaching the sentence that already says it plainly, and at
 * this type size the sentence is not hard to reach.
 */
const STEPS = [
  {
    number: "01",
    title: "Detects",
    body:
      "Watches every Razorpay webhook in real time — payment, subscription, invoice, checkout — and pools bank and method health across every merchant on the network.",
  },
  {
    number: "02",
    title: "Decides",
    body:
      "A contextual bandit learns what works per customer, bank and hour. A T-learner decides whether acting changes the outcome at all, so the cheapest recovery is the one it declines to spend.",
  },
  {
    number: "03",
    title: "Recovers",
    body:
      "Executes through Razorpay rails. Consent, quiet hours and retry ceilings are checked before the send, and every action it took is on the case with the alternatives it rejected.",
  },
];

export function Method() {
  return (
    <section id="method" className="bg-paper px-5 py-24 sm:px-7 sm:py-40">
      <h2 className="type-statement max-w-[18ch] text-ink">The same loop, every case.</h2>

      <ol className="mt-14 border-t border-hairline sm:mt-20">
        {STEPS.map((step) => (
          <li
            key={step.number}
            className="grid grid-cols-1 gap-x-8 gap-y-3 border-b border-hairline py-8 sm:grid-cols-[4rem_14rem_minmax(0,32rem)] sm:py-12"
          >
            <span className="type-meta text-ink-faint">{step.number}</span>
            <h3 className="text-[clamp(1.75rem,3.5vw,3rem)] leading-[0.98] tracking-[-0.035em] text-ink">
              {step.title}
            </h3>
            <p className="text-[15px] leading-[1.4] text-ink-muted">{step.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
