import { Info, RadioTower } from "lucide-react";
import Link from "next/link";

import { isLocal } from "@/lib/env";

export function FirstTimeDashboard() {
  return (
    <div className="rounded-lg border border-hairline bg-elevated p-2">
      <div className="flex flex-col items-center rounded-md bg-subtle px-8 py-20 text-center">
        <RadioTower className="size-24 text-brand" strokeWidth={1} aria-hidden />

        <h2 className="mt-8 font-display text-xl font-semibold tracking-[-0.02em] text-ink">
          Waiting for the first event
        </h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-ink-muted">
          Recover is watching your Razorpay webhook stream. When a payment fails, a cart is
          abandoned, or a subscription mandate breaks, cases will appear here.
        </p>

        {isLocal && (
          <div className="mt-8 flex max-w-md items-start gap-3 rounded-md border border-hairline bg-elevated px-4 py-3 text-left">
            <Info className="mt-0.5 size-4 shrink-0 text-gold" strokeWidth={1.75} aria-hidden />
            <p className="text-sm leading-relaxed text-ink-muted">
              Development mode. Fire a test scenario from the Simulator to see events flow
              through the system.{" "}
              <Link
                href="/app/dev/simulator"
                className="font-medium text-brand underline-offset-4 hover:underline"
              >
                Open Simulator →
              </Link>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
