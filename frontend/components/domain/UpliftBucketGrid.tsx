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

import { UPLIFT_BUCKET_CONFIG } from "@/components/domain/UpliftBucketBadge";
import { StaggeredItem } from "@/components/ui/StaggeredItem";
import type { UpliftBucket, UpliftBucketRow } from "@/lib/api/roi";
import { formatINR, formatPercent } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

/** The scale, in order. `unknown` is not a segment and is not shown here. */
const BUCKET_ORDER: UpliftBucket[] = ["persuadable", "sure_thing", "lost_cause", "dnd"];

function Field({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="text-[10px] tracking-wide text-ink-faint uppercase">{label}</div>
      <div className={cn("font-mono text-sm tabular-nums text-ink", tone)}>{value}</div>
    </div>
  );
}

function EmptyTile({ bucket }: { bucket: UpliftBucket }) {
  const config = UPLIFT_BUCKET_CONFIG[bucket];
  return (
    <div className="rounded-lg border border-dashed border-hairline p-4 opacity-60">
      <h3 className="text-sm font-medium text-ink-muted">{config.label}</h3>
      <p className="mt-1 text-xs text-ink-faint">No cases in this segment yet.</p>
    </div>
  );
}

function BucketTile({ row }: { row: UpliftBucketRow }) {
  const config = UPLIFT_BUCKET_CONFIG[row.bucket] ?? UPLIFT_BUCKET_CONFIG.unknown;
  const harmful = row.estimated_lift < 0;

  return (
    <div className="rounded-lg border border-hairline p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-medium text-ink">{config.label}</h3>
          <p className="mt-0.5 text-xs leading-relaxed text-ink-muted">{config.title}</p>
        </div>
        <span
          className={cn(
            "shrink-0 rounded-4xl px-2 py-0.5 font-mono text-xs tabular-nums",
            harmful ? "bg-danger-subtle text-danger" : config.className,
          )}
        >
          {row.estimated_lift > 0 ? "+" : ""}
          {formatPercent(row.estimated_lift)}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-hairline pt-3 sm:grid-cols-4">
        <Field label="Cases" value={String(row.treated_cases)} />
        <Field label="Treated" value={formatPercent(row.treated_recovery_rate)} />
        <Field label="Control" value={formatPercent(row.control_recovery_rate)} />
        <Field
          label="Incremental"
          value={formatINR(row.incremental_recovery_cents)}
          tone={harmful ? "text-danger" : undefined}
        />
      </div>

      {row.uses_global_control_rate ? (
        <p className="mt-3 flex items-start gap-1.5 text-[11px] leading-relaxed text-ink-faint">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>
            Compared against the overall holdout rate — this segment has{" "}
            {row.control_cases === 0 ? "no" : `only ${row.control_cases}`} controls of its own.
          </span>
        </p>
      ) : null}
    </div>
  );
}

export function UpliftBucketGrid({ rows }: { rows: UpliftBucketRow[] }) {
  const byBucket = new Map(rows.map((row) => [row.bucket, row]));

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {BUCKET_ORDER.map((bucket, index) => {
        const row = byBucket.get(bucket);
        return (
          <StaggeredItem key={bucket} index={index}>
            {row ? <BucketTile row={row} /> : <EmptyTile bucket={bucket} />}
          </StaggeredItem>
        );
      })}
    </div>
  );
}
