import { Inbox } from "lucide-react";
import Link from "next/link";

import { EmptyState } from "@/components/empty-states/EmptyState";
import { isLocal } from "@/lib/env";

/**
 * The cases list with nothing in it.
 *
 * The Simulator link is shown only in local development. In a deployed
 * environment there is no button that manufactures a case — cases arrive from
 * the merchant's own Razorpay traffic — and offering a call to action that does
 * not exist would be worse than offering none.
 */
export function NoCasesYet() {
  return (
    <EmptyState
      icon={Inbox}
      title="No cases yet"
      body="When a payment fails, a cart is abandoned, or a subscription mandate breaks, cases will appear here."
      action={
        isLocal ? (
          <Link
            href="/app/dev/simulator"
            className="rounded-md border border-hairline bg-elevated px-4 py-2 text-sm font-medium text-brand underline-offset-4 hover:underline"
          >
            Fire a scenario from the Simulator →
          </Link>
        ) : undefined
      }
    />
  );
}
