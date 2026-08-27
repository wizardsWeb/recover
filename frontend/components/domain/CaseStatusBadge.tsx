/**
 * The case lifecycle, as colour.
 *
 * Colours are chosen by what the merchant should feel, not by a palette order:
 * open is unresolved (warning), in-flight is the agent working (info),
 * recovered is money back (success), failed is money lost (danger). Stopped is
 * deliberately neutral — the agent standing down because a customer asked it to
 * is correct behaviour, and colouring it as a failure would train merchants to
 * read compliance as loss.
 */

import { Badge } from "@/components/ui/badge";
import type { CaseStatus } from "@/lib/api/cases";

const STATUS_CONFIG: Record<CaseStatus, { label: string; className: string }> = {
  open: { label: "Open", className: "bg-warning-subtle text-warning" },
  in_flight: { label: "In Flight", className: "bg-info-subtle text-info" },
  recovered: { label: "Recovered", className: "bg-success-subtle text-success" },
  stopped: { label: "Stopped", className: "bg-subtle text-ink-faint" },
  failed: { label: "Failed", className: "bg-danger-subtle text-danger" },
  holdout: { label: "Holdout", className: "bg-info-subtle text-info italic" },
};

export function CaseStatusBadge({ status }: { status: CaseStatus }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.open;
  return <Badge className={config.className}>{config.label}</Badge>;
}
