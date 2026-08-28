/**
 * Formatting helpers.
 *
 * Money is stored in paise (integer) everywhere in this system and only ever
 * becomes rupees at the edge, here. The Indian grouping — ₹1,45,000 rather than
 * ₹145,000 — comes from the `en-IN` locale, not from custom string surgery.
 */

const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

const INR_WITH_PAISE = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Format paise as rupees: `formatINR(14500000)` -> `"₹1,45,000"`. */
export function formatINR(paise: number, options?: { showPaise?: boolean }): string {
  const rupees = paise / 100;
  return options?.showPaise ? INR_WITH_PAISE.format(rupees) : INR.format(Math.round(rupees));
}

/** Compact rupees for dense tiles: `"₹1.45L"`, `"₹12.3Cr"`. */
export function formatINRCompact(paise: number): string {
  const rupees = paise / 100;
  const abs = Math.abs(rupees);
  if (abs >= 1_00_00_000) return `₹${(rupees / 1_00_00_000).toFixed(2)}Cr`;
  if (abs >= 1_00_000) return `₹${(rupees / 1_00_000).toFixed(2)}L`;
  if (abs >= 1_000) return `₹${(rupees / 1_000).toFixed(1)}K`;
  return INR.format(Math.round(rupees));
}

const DATE = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const DATE_TIME = new Intl.DateTimeFormat("en-IN", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

function toDate(value: Date | string | number): Date {
  return value instanceof Date ? value : new Date(value);
}

/** `"26 Aug 2026"` */
export function formatDate(value: Date | string | number): string {
  return DATE.format(toDate(value));
}

/** `"26 Aug 2026, 3:47 pm"` */
export function formatDateTime(value: Date | string | number): string {
  return DATE_TIME.format(toDate(value));
}

const RELATIVE = new Intl.RelativeTimeFormat("en-IN", { numeric: "auto" });

const DIVISIONS: Array<{ amount: number; unit: Intl.RelativeTimeFormatUnit }> = [
  { amount: 60, unit: "second" },
  { amount: 60, unit: "minute" },
  { amount: 24, unit: "hour" },
  { amount: 7, unit: "day" },
  { amount: 4.34524, unit: "week" },
  { amount: 12, unit: "month" },
  { amount: Number.POSITIVE_INFINITY, unit: "year" },
];

/** `"3 minutes ago"`, `"yesterday"`, `"in 2 hours"`. */
export function formatRelativeTime(value: Date | string | number, from: Date = new Date()): string {
  let duration = (toDate(value).getTime() - from.getTime()) / 1000;

  for (const division of DIVISIONS) {
    if (Math.abs(duration) < division.amount) {
      return RELATIVE.format(Math.round(duration), division.unit);
    }
    duration /= division.amount;
  }
  return RELATIVE.format(Math.round(duration), "year");
}

/** `"35.2%"` from a 0-1 rate. */
export function formatPercent(rate: number, fractionDigits = 1): string {
  return `${(rate * 100).toFixed(fractionDigits)}%`;
}

/**
 * Format a figure that is already in **rupees**, not paise.
 *
 * Every money column in the database holds paise, so `formatINR` takes paise
 * and that is the right default. The batch simulator is the one exception: its
 * result object is denominated in rupees, because it never touches a money
 * column — it is a simulation whose numbers exist only inside its own JSON.
 * Passing one of those to `formatINR` would render a hundredth of the figure,
 * which is wrong in a way that still looks plausible.
 */
export function formatRupees(rupees: number): string {
  return formatINR(Math.round(rupees * 100));
}

/** Compact rupees for a dense tile, from a rupee figure: `"₹1.45L"`. */
export function formatRupeesCompact(rupees: number): string {
  return formatINRCompact(Math.round(rupees * 100));
}
