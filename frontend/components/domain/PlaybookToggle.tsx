"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/lib/api/client";
import { togglePlaybook } from "@/lib/api/playbooks";

/**
 * The one playbook setting a merchant can change from the UI.
 *
 * Optimistic: the switch moves on click and reverts if the write fails. A
 * toggle that waits on a round trip feels broken at 200ms, and the failure it
 * is guarding against — the request not landing — is both rare and recoverable,
 * because the true state is re-read on the next page load.
 *
 * Turning a playbook off does not touch cases already in flight. Those were
 * opened under the old setting, and closing them would make a settings change
 * destructive; the switch governs what opens next.
 */
export function PlaybookToggle({
  slug,
  label,
  enabled,
}: {
  slug: string;
  label: string;
  enabled: boolean;
}) {
  const router = useRouter();
  const [optimistic, setOptimistic] = useState(enabled);
  const [isPending, startTransition] = useTransition();

  async function onToggle(next: boolean) {
    setOptimistic(next);
    try {
      const result = await togglePlaybook(slug);
      // Trust the server's answer over ours — they agree unless two tabs raced.
      setOptimistic(result.enabled);
      toast.success(`${label} ${result.enabled ? "enabled" : "paused"}`);
      startTransition(() => router.refresh());
    } catch (error) {
      setOptimistic(!next);
      toast.error(error instanceof ApiError ? error.message : "Could not update playbook");
    }
  }

  return (
    <Switch
      checked={optimistic}
      disabled={isPending}
      onCheckedChange={(next) => void onToggle(next)}
      aria-label={`${optimistic ? "Pause" : "Enable"} ${label}`}
    />
  );
}
