import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CreditCard, FileText, RefreshCw, ShoppingCart } from "lucide-react";
import type { ReactNode } from "react";

import { PlaybookToggle } from "@/components/domain/PlaybookToggle";
import { PageHeader } from "@/components/shell/PageHeader";
import type { PlaybookSummary } from "@/lib/api/playbooks";
import { getPlaybooks } from "@/lib/api/playbooks.server";
import { formatINR } from "@/lib/utils/format";

export const metadata: Metadata = { title: "Playbooks" };

const PLAYBOOK_ICONS: Record<string, ReactNode> = {
  failed_payment: <CreditCard size={16} />,
  checkout_abandonment: <ShoppingCart size={16} />,
  subscription_failure: <RefreshCw size={16} />,
  b2b_overdue: <FileText size={16} />,
};

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] tracking-wide text-ink-faint uppercase">{label}</div>
      <div className="font-mono text-sm tabular-nums text-ink">{value}</div>
    </div>
  );
}

function PlaybookCard({ playbook }: { playbook: PlaybookSummary }) {
  const { stats } = playbook;
  const active = stats.casesOpen + stats.casesInFlight;

  return (
    <div
      className={`rounded-lg border border-hairline p-4 transition-opacity ${
        // A paused playbook is dimmed rather than hidden: a merchant needs to
        // see that they switched it off, not wonder where it went.
        playbook.enabled ? "" : "opacity-60"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand-subtle text-brand">
          {PLAYBOOK_ICONS[playbook.slug]}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-medium text-ink">{playbook.label}</h2>
            {!playbook.enabled ? (
              <span className="rounded-4xl bg-warning-subtle px-2 py-0.5 text-[10px] font-medium text-warning">
                Paused
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-xs text-ink-muted">{playbook.description}</p>
        </div>

        <PlaybookToggle
          slug={playbook.slug}
          label={playbook.label}
          enabled={playbook.enabled}
        />
      </div>

      <div className="mt-4 grid grid-cols-4 gap-3 border-t border-hairline pt-3">
        <Stat label="Active" value={String(active)} />
        <Stat label="Total" value={String(stats.totalCases)} />
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
      </div>

      <div className="mt-3 flex items-center justify-between text-xs">
        <span className="text-ink-faint">{playbook.armCount} arms</span>
        <Link
          href={`/app/playbooks/${playbook.slug}`}
          className="flex items-center gap-1 text-brand transition-colors hover:text-brand-hover"
        >
          Configure
          <ArrowRight size={12} />
        </Link>
      </div>
    </div>
  );
}

export default async function PlaybooksPage() {
  const { playbooks } = await getPlaybooks();

  return (
    <>
      <PageHeader
        title="Playbooks"
        subtitle="How the agent responds to each kind of leak"
      />

      <div className="grid gap-4 lg:grid-cols-2">
        {playbooks.map((playbook) => (
          <PlaybookCard key={playbook.slug} playbook={playbook} />
        ))}
      </div>

      <p className="mt-6 text-xs text-ink-faint">
        Pausing a playbook stops new cases opening under it. Cases already in flight
        continue — they were opened under the old setting, and closing them here
        would make a settings change destructive.
      </p>
    </>
  );
}
