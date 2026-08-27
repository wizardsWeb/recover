/**
 * Pre-computed bandit convergence data for the batch screen.
 *
 * Phase 11 replaces this with a real batch run: a thousand synthetic cases
 * pushed through the agent, posteriors updated case by case, the curve drawn
 * from what actually happened. Until then the screen shows this, and says so on
 * the page — an unlabelled synthetic curve presented as a measurement is the
 * one thing a demo must not do.
 *
 * The shape is the argument, and it is the honest shape rather than a
 * flattering one: the bandit *loses* for the first ~200 cases. It is exploring,
 * and exploration costs real recoveries. A curve that started above the
 * baseline would be describing a system that already knew the answer, which is
 * precisely the thing a bandit is for not needing.
 */

export interface CurvePoint {
  /** Cases seen so far. */
  cases: number;
  /** Recovery rate, in percent. */
  bandit: number;
  baseline: number;
}

export interface CurveAnnotation {
  cases: number;
  label: string;
}

export const BANDIT_CURVE: CurvePoint[] = [
  { cases: 0, bandit: 20.0, baseline: 22.0 },
  { cases: 50, bandit: 19.5, baseline: 21.8 },
  { cases: 100, bandit: 20.8, baseline: 22.1 },
  { cases: 150, bandit: 22.4, baseline: 22.0 },
  { cases: 200, bandit: 24.6, baseline: 21.9 },
  { cases: 250, bandit: 27.3, baseline: 22.2 },
  { cases: 300, bandit: 29.8, baseline: 22.0 },
  { cases: 400, bandit: 32.7, baseline: 21.8 },
  { cases: 500, bandit: 34.9, baseline: 22.1 },
  { cases: 600, bandit: 36.1, baseline: 22.0 },
  { cases: 700, bandit: 37.0, baseline: 21.9 },
  { cases: 800, bandit: 37.8, baseline: 22.0 },
  { cases: 900, bandit: 38.0, baseline: 22.1 },
  { cases: 1000, bandit: 38.2, baseline: 22.0 },
];

/** What the bandit worked out, and roughly when. */
export const CURVE_ANNOTATIONS: CurveAnnotation[] = [
  { cases: 140, label: "Learned: silent retry beats late-night HDFC" },
  { cases: 280, label: "Learned: 8% beats 12% for ₹1,000–1,500 carts" },
  { cases: 420, label: "Learned: promise-to-pay deserves 5-day pause" },
  { cases: 600, label: "Federated priors imported" },
];

/** Where the bandit overtakes the fixed rule for good. */
export const CROSSOVER_AT_CASE = 200;

/** Final gap between the two series, in percentage points. */
export const LIFT_PP = 16.2;

/**
 * The closing numbers from scenarios.md, in paise.
 *
 * ``incremental`` is the number that matters and is far below ``gross``: some of
 * what a recovery agent "recovers" would have arrived on its own, and counting
 * that as earned is the standard way these tools overstate themselves. The gap
 * between the two is what the Phase 9 uplift model exists to measure.
 */
export const BATCH_SUMMARY = {
  atRiskCents: 420_000_000,
  grossRecoveredCents: 148_000_000,
  incrementalRecoveredCents: 92_000_000,
  casesSimulated: 1000,
};
