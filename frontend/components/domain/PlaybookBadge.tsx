/** Which of the four recovery playbooks a case belongs to. */

import { CreditCard, FileText, RefreshCw, ShoppingCart } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";

const PLAYBOOK_CONFIG: Record<string, { label: string; className: string; icon: LucideIcon }> = {
  failed_payment: {
    label: "Failed Payment",
    className: "bg-danger-subtle text-danger",
    icon: CreditCard,
  },
  checkout_abandonment: {
    label: "Cart Abandonment",
    className: "bg-warning-subtle text-warning",
    icon: ShoppingCart,
  },
  subscription_failure: {
    label: "Subscription",
    className: "bg-info-subtle text-info",
    icon: RefreshCw,
  },
  b2b_overdue: {
    label: "B2B Invoice",
    className: "bg-brand-subtle text-brand",
    icon: FileText,
  },
};

/**
 * The icon carries the playbook at a glance and the label confirms it.
 *
 * Both, not one: four coloured badges in a column are four colours a merchant
 * has to have learned, and four icons without labels are four rebuses. The pair
 * costs 16px and means the badge is readable on first encounter.
 */
export function PlaybookBadge({ playbook }: { playbook: string }) {
  const config = PLAYBOOK_CONFIG[playbook];
  // An unknown playbook renders its raw name rather than nothing: a case the UI
  // does not recognise is exactly the case someone needs to see.
  if (!config) return <Badge className="bg-subtle text-ink-faint">{playbook}</Badge>;

  const Icon = config.icon;
  return (
    <Badge className={config.className}>
      <Icon aria-hidden />
      {config.label}
    </Badge>
  );
}
