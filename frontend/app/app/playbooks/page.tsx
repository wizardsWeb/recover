import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CreditCard, FileText, RefreshCw, ShoppingCart } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { RazorpayGlyph } from "@/components/brand/RazorpayGlyph";
import { PlaybookToggle } from "@/components/domain/PlaybookToggle";
import { PageHeader } from "@/components/shell/PageHeader";
import { LiftCard } from "@/components/ui/LiftCard";
import { StaggerList } from "@/components/ui/StaggerList";
import type { PlaybookSummary } from "@/lib/api/playbooks";
import { getPlaybooks } from "@/lib/api/playbooks.server";
import { formatINR } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

export const metadata: Metadata = { title: "Playbooks" };

/**
 * Each playbook's icon and tint.
 *
 * The same four semantic colours `PlaybookBadge` uses, so a merchant who has
 * learned that amber means "cart abandonment" in a table finds the same amber
 * on the card here. A card grid with its own palette would be a second thing to
 * learn for no gain.
 */
const PLAYBOOK_STYLE: Record<
  string,
  { icon: LucideIcon; chip: string; tint: string; rule: string; rail: string }
> = {
  failed_payment: {
    icon: CreditCard,
    chip: "bg-danger-subtle text-danger",
    tint: "from-danger/[0.04]",
    rule: "border-l-danger",
    rail: "Razorpay Payment Gateway",
  },
  checkout_abandonment: {
    icon: ShoppingCart,
    chip: "bg-warning-subtle text-warning",
    tint: "from-warning/[0.04]",
    rule: "border-l-warning",
    rail: "Razorpay Payment Links",
  },
  subscription_failure: {
    icon: RefreshCw,
    chip: "bg-info-subtle text-info",
    tint: "from-info/[0.04]",
    rule: "border-l-info",
    rail: "Razorpay Subscriptions",
  },
  b2b_overdue: {
    icon: FileText,
    chip: "bg-brand-subtle text-brand",
    tint: "from-brand/[0.04]",
    rule: "border-l-brand",
    rail: "RazorpayX",
  },
};

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] tracking-[0.06em] text-ink-faint uppercase">{label}</dt>
      <dd className="mt-0.5 font-display text-lg font-semibold text-ink tabular-nums">{value}</dd>
    </div>
  );
}

function PlaybookCard({ playbook }: { playbook: PlaybookSummary }) {
  const { stats } = playbook;
  const style = PLAYBOOK_STYLE[playbook.slug];
  const Icon = style?.icon ?? CreditCard;
  const active = stats.casesOpen + stats.casesInFlight;

  return (
    <LiftCard staggered effect="scale">
      <div
        className={cn(
          "h-full rounded-card border border-hairline border-l-[3px] bg-elevated bg-gradient-to-br to-transparent p-5 shadow-card",
          style?.tint,
          style?.rule,
          // A paused playbook is dimmed rather than hidden: a merchant needs to
          // see that they switched it off, not wonder where it went.
          !playbook.enabled && "opacity-60",
        )}
      >
        <div className="flex items-start gap-3">
          <span
            className={cn(
              "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
              style?.chip,
            )}
          >
            <Icon className="size-4" strokeWidth={1.75} aria-hidden />
          </span>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h2 className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
                {playbook.label}
              </h2>
              {!playbook.enabled ? (
                <span className="rounded-4xl bg-warning-subtle px-2 py-0.5 text-[10px] font-medium text-warning">
                  Paused
                </span>
              ) : null}
            </div>
            <p className="mt-1 text-sm leading-relaxed text-ink-muted">{playbook.description}</p>
          </div>

          {/* The switch sits in the header, aligned with the title rather than
              buried in the footer with the link: it is the one control on the
              card, and a control that changes what the card describes belongs
              beside the description. */}
          <PlaybookToggle slug={playbook.slug} label={playbook.label} enabled={playbook.enabled} />
        </div>

        <dl className="mt-5 grid grid-cols-3 gap-3 border-t border-hairline pt-4">
          <Stat label="Active" value={String(active)} />
          <Stat
            label="Recovered"
            value={
              // A rate over zero cases is not 0% — it is unmeasured, and a bold
              // "0%" beside an untouched playbook reads as failure.
              stats.totalCases > 0 ? `${Math.round(stats.recoveryRate * 100)}%` : "—"
            }
          />
          <Stat
            label="At risk"
            value={stats.amountAtRiskCents > 0 ? formatINR(stats.amountAtRiskCents) : "—"}
          />
        </dl>

        {/* Which Razorpay product this playbook executes through. On the card
            rather than only in the docs, because "how does it actually recover
            the money" is the first question a reader has about a playbook. */}
        <div className="mt-4 flex items-center gap-1.5 border-t border-hairline pt-3">
          <RazorpayGlyph className="size-3.5" />
          <span className="text-[11px] font-medium text-ink-muted">{style?.rail}</span>
        </div>

        <div className="mt-3 flex items-center justify-between text-xs">
          <span className="font-mono text-ink-faint">
            {playbook.armCount} arms · {stats.totalCases} cases
          </span>
          <Link
            href={`/app/playbooks/${playbook.slug}`}
            className="flex items-center gap-1 font-medium text-brand transition-colors hover:text-brand-hover"
          >
            Configure
            <ArrowRight className="size-3" aria-hidden />
          </Link>
        </div>
      </div>
    </LiftCard>
  );
}

export default async function PlaybooksPage() {
  const { playbooks } = await getPlaybooks();

  return (
    <>
      <PageHeader title="Playbooks" subtitle="How the agent responds to each kind of leak" />

      <StaggerList stagger={0.08} className="grid gap-4 lg:grid-cols-2">
        {playbooks.map((playbook) => (
          <PlaybookCard key={playbook.slug} playbook={playbook} />
        ))}
      </StaggerList>

      <p className="mt-6 text-xs text-ink-faint">
        Pausing a playbook stops new cases opening under it. Cases already in flight continue — they
        were opened under the old setting, and closing them here would make a settings change
        destructive.
      </p>
    </>
  );
}
