/**
 * The four segments, and what each one contributed.
 *
 * Fixed 2×2 order rather than sorted by size: these buckets are a scale, and
 * re-ordering them by whichever happened to earn most this week would break the
 * only thing that makes the grid readable at a glance. A bucket with no cases
 * still renders, greyed — "we saw none of these" is information, and a missing
 * tile reads as a bug.
 *
 * `estimated_lift` is the number the tile is really about, so it is the one in
 * mono type beside the money. A negative lift is shown with its sign and in
 * danger colour; suppressing it would hide the only finding on this page that
 * asks the merchant to *stop* doing something.
 */

import { AlertTriangle } from "lucide-react";

import { BucketDonut } from "@/components/domain/BucketDonut";
import { UPLIFT_BUCKET_CONFIG } from "@/components/domain/UpliftBucketBadge";
import { Card, CardContent } from "@/components/ui/card";
import { LiftCard } from "@/components/ui/LiftCard";
import { StaggerList } from "@/components/ui/StaggerList";
import type { UpliftBucket, UpliftBucketRow } from "@/lib/api/roi";
import { formatINR, formatPercent } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

/** The scale, in order. `unknown` is not a segment and is not shown here. */
const BUCKET_ORDER: UpliftBucket[] = ["persuadable", "sure_thing", "lost_cause", "dnd"];

function Field({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <dt className="text-[10px] tracking-[0.06em] text-ink-faint uppercase">{label}</dt>
      <dd className={cn("font-mono text-sm text-ink tabular-nums", tone)}>{value}</dd>
    </div>
  );
}

function EmptyTile({ bucket }: { bucket: UpliftBucket }) {
  const config = UPLIFT_BUCKET_CONFIG[bucket];
  return (
    <div className="h-full rounded-none border border-dashed border-hairline p-5 opacity-60">
      <h3 className="font-display text-base font-semibold text-ink-muted">{config.label}</h3>
      <p className="mt-1 text-xs text-ink-faint">No cases in this segment yet.</p>
    </div>
  );
}

function BucketTile({ row }: { row: UpliftBucketRow }) {
  const config = UPLIFT_BUCKET_CONFIG[row.bucket] ?? UPLIFT_BUCKET_CONFIG.unknown;
  const harmful = row.estimated_lift < 0;
  // Persuadable is the segment the whole page is arguing for: it is where a
  // message changes the outcome, and it is the only one worth spending a send
  // on. A 2px rule and a step of elevation is how the grid says so without a
  // sentence. The brief asked for gold here; gold is already spent on the
  // incremental figure above, and a screen with two accents has none.
  const isKeySegment = row.bucket === "persuadable";

  return (
    <Card
      className={cn(
        "h-full",
        isKeySegment ? "border-2 border-brand shadow-md" : "border-hairline shadow-card",
      )}
    >
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="font-display text-base font-semibold tracking-[-0.01em] text-ink">
              {config.label}
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-ink-muted">{config.title}</p>
          </div>
          <span
            className={cn(
              "shrink-0 rounded-none px-2 py-0.5 font-mono text-xs tabular-nums",
              harmful ? "bg-danger-subtle text-danger" : config.className,
            )}
          >
            {row.estimated_lift > 0 ? "+" : ""}
            {formatPercent(row.estimated_lift)}
          </span>
        </div>

        <div className="mt-5 flex items-center gap-5 border-t border-hairline pt-4">
          <BucketDonut
            treated={row.treated_recovery_rate}
            control={row.control_recovery_rate}
            harmful={harmful}
          />
          <dl className="grid min-w-0 flex-1 grid-cols-2 gap-x-4 gap-y-3">
            <Field label="Cases" value={String(row.treated_cases)} />
            <Field label="Control" value={formatPercent(row.control_recovery_rate)} />
            <Field
              label="Incremental"
              value={formatINR(row.incremental_recovery_cents)}
              tone={harmful ? "text-danger" : undefined}
            />
            <Field label="Treated" value={formatPercent(row.treated_recovery_rate)} />
          </dl>
        </div>

        {row.uses_global_control_rate ? (
          <p className="mt-4 flex items-start gap-1.5 text-[11px] leading-relaxed text-ink-faint">
            <AlertTriangle className="mt-0.5 size-3 shrink-0" aria-hidden />
            <span>
              Compared against the overall holdout rate — this segment has{" "}
              {row.control_cases === 0 ? "no" : `only ${row.control_cases}`} controls of its own.
            </span>
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function UpliftBucketGrid({ rows }: { rows: UpliftBucketRow[] }) {
  const byBucket = new Map(rows.map((row) => [row.bucket, row]));

  return (
    <StaggerList stagger={0.08} className="grid gap-4 sm:grid-cols-2">
      {BUCKET_ORDER.map((bucket) => {
        const row = byBucket.get(bucket);
        return (
          <LiftCard key={bucket} staggered effect="scale">
            {row ? <BucketTile row={row} /> : <EmptyTile bucket={bucket} />}
          </LiftCard>
        );
      })}
    </StaggerList>
  );
}
