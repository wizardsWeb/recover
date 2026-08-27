/** Which of the four recovery playbooks a case belongs to. */

import { Badge } from "@/components/ui/badge";

const PLAYBOOK_CONFIG: Record<string, { label: string; className: string }> = {
  failed_payment: { label: "Failed Payment", className: "bg-danger-subtle text-danger" },
  checkout_abandonment: { label: "Cart Abandonment", className: "bg-warning-subtle text-warning" },
  subscription_failure: { label: "Subscription", className: "bg-info-subtle text-info" },
  b2b_overdue: { label: "B2B Invoice", className: "bg-brand-subtle text-brand" },
};

export function PlaybookBadge({ playbook }: { playbook: string }) {
  const config = PLAYBOOK_CONFIG[playbook];
  // An unknown playbook renders its raw name rather than nothing: a case the UI
  // does not recognise is exactly the case someone needs to see.
  if (!config) return <Badge className="bg-subtle text-ink-faint">{playbook}</Badge>;
  return <Badge className={config.className}>{config.label}</Badge>;
}
