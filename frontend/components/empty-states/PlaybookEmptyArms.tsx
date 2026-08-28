import { Sprout } from "lucide-react";

import { EmptyState } from "@/components/empty-states/EmptyState";

/**
 * A playbook whose bandit has no posteriors in any context yet.
 *
 * Distinct from an arm that has been pulled and lost: this says the agent has
 * no evidence at all, which is why the arms list is blank rather than showing
 * every arm sitting at the 0.5 a Beta(1,1) prior implies. Rendering that would
 * present an untouched arm as a measured coin flip.
 */
export function PlaybookEmptyArms() {
  return (
    <EmptyState
      compact
      icon={Sprout}
      title="Bandit hasn't learned yet"
      body="Run cases through this playbook to see which arms the bandit discovers."
    />
  );
}
