import type { Vertical } from "@/lib/supabase/types";

/**
 * The vertical set is frozen in the migration's CHECK constraint and mirrored
 * in the backend's `Vertical` Literal. Labels live here so onboarding and
 * settings cannot drift.
 */
export const VERTICALS: ReadonlyArray<{ value: Vertical; label: string; hint: string }> = [
  {
    value: "d2c_beauty",
    label: "Beauty and personal care",
    hint: "Direct-to-consumer, mostly one-off carts",
  },
  {
    value: "edtech_subscription",
    label: "Edtech and subscriptions",
    hint: "Recurring mandates and renewals",
  },
  {
    value: "b2b_distribution",
    label: "B2B and distribution",
    hint: "Invoices, credit terms, larger tickets",
  },
  {
    value: "other",
    label: "Something else",
    hint: "We will infer the playbook mix from your traffic",
  },
];

export function verticalLabel(vertical: Vertical | null): string {
  return VERTICALS.find((entry) => entry.value === vertical)?.label ?? "Not set";
}

/** The IANA zones an Indian merchant plausibly operates in. */
export const TIMEZONES = [
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Europe/London",
  "America/New_York",
  "UTC",
] as const;
