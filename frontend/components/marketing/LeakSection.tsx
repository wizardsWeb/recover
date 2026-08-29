"use client";

import { CreditCard, FileClock, RefreshCcw, ShoppingCart } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { AnimatedNumber } from "@/components/ui/AnimatedNumber";
import { StaggerItem, StaggerList } from "@/components/ui/StaggerList";

interface Leak {
  icon: LucideIcon;
  /** Crores per day across the market, which is what the figure below shows. */
  amount: number;
  unit: string;
  title: string;
  body: string;
}

/**
 * The four leaks, in the order the playbooks are numbered.
 *
 * The figures are daily market-wide estimates, not a merchant's own losses —
 * they are labelled as such, because a landing page quoting a number the reader
 * will assume is theirs has borrowed credibility it cannot repay.
 */
const LEAKS: Leak[] = [
  {
    icon: CreditCard,
    amount: 4.2,
    unit: "L/day",
    title: "Payments that fail",
    body: "A declined card, a timed-out OTP, a bank that was down for ninety seconds.",
  },
  {
    icon: ShoppingCart,
    amount: 6.8,
    unit: "L/day",
    title: "Carts left at checkout",
    body: "The intent was there. Something between the button and the bank took it away.",
  },
  {
    icon: RefreshCcw,
    amount: 3.1,
    unit: "L/day",
    title: "Mandates that stop",
    body: "Three failures on the 1st is a salary-cycle problem, not a churned customer.",
  },
  {
    icon: FileClock,
    amount: 9.4,
    unit: "L/day",
    title: "Invoices that run late",
    body: "A buyer who always pays late and always pays needs a different message.",
  },
];

/**
 * Section two: what the product is for.
 *
 * Permanently dark, in both colour modes. The landing page alternates dark and
 * light bands the way a deck alternates slides, and a band that inverted with
 * the reader's theme would break the rhythm on half of all visits.
 *
 * The cards are glass — white at 4% over the section ground — rather than solid
 * panels. Four solid cards on near-black read as four holes cut in the page;
 * a translucent fill keeps them sitting *on* the ground they share.
 */
export function LeakSection() {
  return (
    <section id="leaks" className="scroll-mt-24 bg-ink-900 py-24 sm:py-32">
      <div className="mx-auto max-w-6xl px-6">
        <h2 className="max-w-2xl font-display text-4xl leading-[1.1] font-semibold tracking-[-0.03em] text-white sm:text-5xl">
          Revenue doesn&rsquo;t vanish. It slips.
        </h2>
        <p className="mt-4 max-w-xl text-base leading-relaxed text-white/55">
          Four leaks, four causes, four different fixes. Estimated market-wide, per day — the point
          is the shape of the problem, not the size of your share of it.
        </p>

        <StaggerList as="ul" stagger={0.1} className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {LEAKS.map((leak) => {
            const Icon = leak.icon;
            return (
              <StaggerItem
                key={leak.title}
                as="li"
                className="rounded-card border border-white/[0.08] bg-white/[0.04] p-6"
              >
                <Icon
                  className="size-12 text-brand-on-dark"
                  strokeWidth={1.25}
                  aria-hidden
                />
                <p className="mt-6 font-display text-4xl font-bold tracking-[-0.03em] text-white tabular-nums">
                  <AnimatedNumber
                    value={leak.amount}
                    startOnView
                    format={(n) => `₹${n.toFixed(1)}${leak.unit}`}
                  />
                </p>
                <h3 className="mt-3 text-sm font-medium text-white">{leak.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-white/60">{leak.body}</p>
              </StaggerItem>
            );
          })}
        </StaggerList>
      </div>
    </section>
  );
}
