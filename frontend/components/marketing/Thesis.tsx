/**
 * The statement, and two columns of what it is made of.
 *
 * The colossal line is set to overflow the right edge of the viewport at large
 * sizes and that is intentional, not a bug to be clamped: the reference does
 * exactly this, and a phrase that runs off the page reads as a fragment of
 * something larger rather than as a heading sized to fit its box.
 *
 * Under it, two lists in the left-middle of the grid with the whole right side
 * left empty. Asymmetry is the point — a centred pair of columns would be a
 * feature grid, and this is an index of capabilities.
 *
 * The lists are comma-joined prose rather than bulleted items. Bullets would
 * make each phrase a claim of its own; a comma list reads as one breath and is
 * how a studio names what it does.
 */
const COLUMNS = [
  {
    label: "Diagnosis",
    body:
      "Causal graph traversal, Bayesian posteriors over named causes, evidence and risk factors, per-playbook hypotheses",
  },
  {
    label: "Recovery",
    body:
      "Contextual bandit decisions, uplift gating, RBI and TRAI guardrails, execution on Razorpay rails, append-only audit",
  },
];

export function Thesis() {
  return (
    <section className="bg-paper py-24 sm:py-40">
      {/* `overflow-hidden` on the section, not on the heading: the heading is
          meant to be cut off by the viewport, and clipping it here is what makes
          that a crop rather than a horizontal scrollbar. */}
      <div className="overflow-hidden">
        <h2 className="type-colossal px-5 whitespace-nowrap text-ink sm:px-7">
          Systematic recovery
        </h2>
      </div>

      <div className="mt-14 grid gap-10 px-5 sm:mt-20 sm:grid-cols-12 sm:px-7">
        {COLUMNS.map((column, index) => (
          <div
            key={column.label}
            className={index === 0 ? "sm:col-span-4 sm:col-start-4" : "sm:col-span-4 sm:col-start-8"}
          >
            <p className="type-meta text-ink">{column.label}</p>
            <p className="mt-2 text-[13px] leading-[1.35] text-ink-muted">{column.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
