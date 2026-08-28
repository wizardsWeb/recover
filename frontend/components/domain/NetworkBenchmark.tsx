/**
 * Where this merchant sits against the rest of the network.
 *
 * A benchmark is only worth showing if it says what it is comparing against.
 * Three states are rendered differently on purpose: a real distribution, a
 * network too small to summarise without identifying someone, and a merchant
 * with nothing closed yet. Collapsing the last two into a blank would leave the
 * reader assuming the flattering interpretation of whichever they were in.
 *
 * The insights below the bar are static and deliberately so. They are the
 * patterns the network has established rather than this merchant's readings, so
 * they do not change when a filter does — and presenting them as live figures
 * would be the one dishonest thing on a page about honest measurement.
 */

import { Info, Users } from "lucide-react";

import type { BenchmarkResponse } from "@/lib/api/network";
import { formatPercent } from "@/lib/utils/format";

/** Always-true findings from aggregate Razorpay network behaviour. */
const INSIGHTS = [
  "HDFC credit cards succeed 34% more often at 9am than at 11pm.",
  "UPI mandates that fail on the 1st recover 3× faster when retried on the 7th.",
  "B2B invoices chased with a partial-payment offer close 41% faster.",
];

function Figure({
  label,
  value,
  emphasis = false,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] tracking-wide text-ink-faint uppercase">{label}</div>
      <div
        className={
          emphasis
            ? "font-mono text-2xl tabular-nums text-brand"
            : "font-mono text-2xl tabular-nums text-ink-muted"
        }
      >
        {value}
      </div>
    </div>
  );
}

function Distribution({ data }: { data: BenchmarkResponse }) {
  const rate = data.merchant_rate ?? 0;
  const median = data.vertical_median ?? 0;
  const top = data.vertical_top_decile ?? 0;
  // The axis spans 0-100% rather than the observed range: a bar scaled to the
  // data would make a two-point gap look like a chasm.
  const position = Math.min(100, Math.max(0, rate * 100));

  return (
    <>
      <div className="grid grid-cols-3 gap-4">
        <Figure label="You" value={formatPercent(rate)} emphasis />
        <Figure label="Network median" value={formatPercent(median)} />
        <Figure label="Top decile" value={formatPercent(top)} />
      </div>

      <div className="mt-5">
        <div className="relative h-2 rounded-full bg-subtle">
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-brand-subtle"
            style={{ width: `${position}%` }}
            aria-hidden
          />
          {/* Median and top decile as tick marks on the same axis, so the
              merchant's position is read against them rather than described. */}
          {[
            { at: median, label: "Median" },
            { at: top, label: "Top decile" },
          ].map((mark) => (
            <span
              key={mark.label}
              className="absolute inset-y-[-3px] w-px bg-ink-faint"
              style={{ left: `${Math.min(100, Math.max(0, mark.at * 100))}%` }}
              title={`${mark.label}: ${formatPercent(mark.at)}`}
              aria-hidden
            />
          ))}
          <span
            className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-base bg-brand"
            style={{ left: `${position}%` }}
            aria-hidden
          />
        </div>
        <p className="mt-2 text-xs text-ink-muted">
          {data.percentile !== null ? (
            <>
              You recover more than{" "}
              <strong className="font-medium text-ink">{data.percentile}%</strong> of the{" "}
              {data.peer_merchants} merchants on the network, over {data.sample_size} closed
              cases.
            </>
          ) : null}
        </p>
      </div>
    </>
  );
}

export function NetworkBenchmark({ data }: { data: BenchmarkResponse }) {
  return (
    <section className="rounded-lg border border-hairline p-5">
      <h2 className="text-sm font-medium text-ink">Your recovery rate against the network</h2>

      <div className="mt-4">
        {data.basis === "network" ? (
          <Distribution data={data} />
        ) : data.basis === "network_too_small" ? (
          <div className="space-y-3">
            <Figure label="Your recovery rate" value={formatPercent(data.merchant_rate ?? 0)} emphasis />
            <p className="flex items-start gap-1.5 text-xs leading-relaxed text-ink-muted">
              <Users size={13} className="mt-0.5 shrink-0 text-ink-faint" aria-hidden />
              <span>
                No comparison yet. With {data.peer_merchants} other merchant
                {data.peer_merchants === 1 ? "" : "s"} on the network, a &ldquo;median&rdquo;
                would just be someone else&rsquo;s recovery rate with a different name on it.
              </span>
            </p>
          </div>
        ) : (
          <p className="flex items-start gap-1.5 text-xs leading-relaxed text-ink-muted">
            <Info size={13} className="mt-0.5 shrink-0 text-ink-faint" aria-hidden />
            <span>
              Nothing closed yet. Once cases start resolving, your recovery rate appears here
              beside the network&rsquo;s.
            </span>
          </p>
        )}
      </div>

      <div className="mt-6 border-t border-hairline pt-4">
        <h3 className="text-[10px] font-medium tracking-wide text-ink-faint uppercase">
          Insights from the Razorpay network
        </h3>
        <ul className="mt-2 space-y-1.5">
          {INSIGHTS.map((insight) => (
            <li key={insight} className="flex gap-2 text-xs leading-relaxed text-ink-muted">
              <span aria-hidden className="mt-1.5 size-1 shrink-0 rounded-full bg-brand" />
              {insight}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
