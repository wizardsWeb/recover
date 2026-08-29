/**
 * The causal segment, as colour.
 *
 * The scale runs by *what the agent should do*, not by how good the customer
 * looks. A persuadable customer is the one worth a message, so it takes the
 * brand colour. A sure thing is a recovery the agent did not cause — neutral,
 * because treating it as a win is the mistake this whole page exists to
 * prevent. A lost cause is wasted effort, and `dnd` is the only bucket where
 * acting does harm, so it is the only one coloured as danger.
 *
 * `unknown` is not an error state. Every case closed before a model existed
 * carries it, and so does every case from a merchant whose holdout group has
 * not resolved yet — which is the normal state in week one.
 */

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { UpliftBucket } from "@/lib/api/roi";
import { cn } from "@/lib/utils/cn";

interface BucketConfig {
  label: string;
  className: string;
  /** What the bucket means, for the badge's tooltip. */
  title: string;
}

export const UPLIFT_BUCKET_CONFIG: Record<UpliftBucket, BucketConfig> = {
  persuadable: {
    label: "Persuadable",
    className: "bg-brand-subtle text-brand",
    title: "Recovers materially more often when contacted. The message is what earns the money.",
  },
  sure_thing: {
    label: "Sure thing",
    className: "bg-subtle text-ink-muted",
    title:
      "Likely to pay with or without a message. Still contacted — the send is nearly free — but the recovery is not counted as caused by the agent.",
  },
  lost_cause: {
    label: "Lost cause",
    className: "bg-subtle text-ink-faint",
    title: "Recovers at the same low rate treated or not. No message is sent.",
  },
  dnd: {
    label: "Do not disturb",
    className: "bg-danger-subtle text-danger",
    title: "Recovers less often when contacted. The message is what drives them away.",
  },
  unknown: {
    label: "Unmeasured",
    className: "bg-subtle text-ink-faint italic",
    title: "No uplift model for this playbook yet — not enough resolved holdout cases to estimate.",
  },
};

interface UpliftBucketBadgeProps {
  /** The raw column value. Anything unrecognised renders as `unknown`. */
  bucket: string | null | undefined;
  className?: string;
}

export function UpliftBucketBadge({ bucket, className }: UpliftBucketBadgeProps) {
  const config = UPLIFT_BUCKET_CONFIG[bucket as UpliftBucket] ?? UPLIFT_BUCKET_CONFIG.unknown;
  return (
    // The label alone is a category name; the tooltip is what the category
    // means. `tabIndex` makes it reachable, which the `title` attribute it
    // replaces never was.
    <Tooltip>
      <TooltipTrigger render={<Badge tabIndex={0} className={cn(config.className, className)} />}>
        {config.label}
      </TooltipTrigger>
      <TooltipContent>{config.title}</TooltipContent>
    </Tooltip>
  );
}
