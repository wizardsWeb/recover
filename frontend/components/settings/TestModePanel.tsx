"use client";

import { AlertTriangle, Check, Copy, ShieldCheck, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fetchRazorpayStatus, type RazorpayStatus } from "@/lib/api/integrations";
import { ApiError } from "@/lib/api/client";
import { fireScenario } from "@/lib/api/simulator";
import { cn } from "@/lib/utils/cn";

/**
 * Razorpay's published test cards.
 *
 * These are from Razorpay's own public documentation and are not secrets — they
 * are the same six numbers in every integration guide. They are hard-coded
 * rather than fetched because there is no endpoint that serves them and a
 * network call to display a constant is a network call that can fail.
 *
 * The outcome column is the detail that trips people up on a first demo: these
 * cards do not succeed or fail on their own. Razorpay shows a mock bank page
 * with Success and Failure buttons, and the tester picks. A card labelled
 * "always succeeds" would send someone hunting for a card that does not exist.
 */
const TEST_CARDS = [
  { network: "Visa", region: "Domestic", number: "4111 1111 1111 1111" },
  { network: "Mastercard", region: "Domestic", number: "5104 0600 0000 0008" },
  { network: "Visa", region: "International", number: "4239 5360 0631 5640" },
];

/** UPI handles, which unlike the cards do resolve on their own. */
const TEST_UPI = [
  { vpa: "success@razorpay", outcome: "Succeeds immediately", tone: "success" as const },
  { vpa: "failure@razorpay", outcome: "Fails immediately", tone: "danger" as const },
];

function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      // Long enough to register, short enough that the button is ready again
      // before a tester has finished pasting.
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // `navigator.clipboard` needs a secure context and a user gesture, and
      // over plain HTTP on a LAN address it is simply absent. Saying so beats a
      // button that does nothing.
      toast.error("Could not copy", { description: "Select the value and copy it manually." });
    }
  }, [value]);

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={() => void copy()}
      aria-label={`Copy ${label}`}
      className="shrink-0"
    >
      {copied ? (
        <Check className="text-success" aria-hidden />
      ) : (
        <Copy className="text-ink-faint" aria-hidden />
      )}
    </Button>
  );
}

function StatusRow({
  label,
  ok,
  detail,
  warning,
}: {
  label: string;
  ok: boolean;
  detail: string;
  /** Shown instead of `detail` when not ok — what to actually do about it. */
  warning?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-hairline py-3 last:border-b-0">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">{label}</p>
        <p className="mt-0.5 text-xs text-ink-muted">{!ok && warning ? warning : detail}</p>
      </div>
      <Badge
        className={cn(
          "shrink-0",
          ok ? "bg-success-subtle text-success" : "bg-warning-subtle text-warning",
        )}
      >
        {ok ? <Check aria-hidden /> : <AlertTriangle aria-hidden />}
        {ok ? "Configured" : "Not set"}
      </Badge>
    </div>
  );
}

/**
 * The tab a judge or a tester opens before running the demo.
 *
 * Two jobs, and they are why it is one panel rather than two. It carries the
 * credentials needed to complete a payment on the mock checkout, and it says
 * whether this deployment is actually wired to Razorpay — because a demo where
 * the payment link is simulated and a demo where it is real look identical until
 * someone clicks the link.
 */
export function TestModePanel() {
  const [status, setStatus] = useState<RazorpayStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const [firing, setFiring] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void fetchRazorpayStatus()
      .then((next) => {
        if (!cancelled) setStatus(next);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function fireTestWebhook() {
    setFiring(true);
    try {
      const result = await fireScenario("S3");
      toast.success("Test event fired", {
        description: `payment.failed accepted — case ${result.caseId?.slice(0, 8) ?? "opening"}.`,
      });
    } catch (error) {
      toast.error(
        error instanceof ApiError && error.status === 424
          ? "Load fixtures first"
          : "Could not fire the test event",
        {
          description:
            error instanceof Error ? error.message : "The simulator did not respond.",
        },
      );
    } finally {
      setFiring(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* ---- Wiring status ---------------------------------------------------
          First, because everything below is only interesting if this says the
          integration is live. */}
      <section className="rounded-none border border-hairline bg-elevated p-5 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
              Razorpay connection
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              Whether this deployment makes real API calls, read from the server&rsquo;s own
              settings.
            </p>
          </div>
          {status ? (
            <Badge
              className={cn(
                status.mode === "test"
                  ? "bg-info-subtle text-info"
                  : status.mode === "live"
                    ? "bg-danger-subtle text-danger"
                    : "bg-subtle text-ink-faint",
              )}
            >
              {status.mode === "unconfigured" ? "No keys" : `${status.mode} mode`}
            </Badge>
          ) : null}
        </div>

        <div className="mt-4">
          {failed ? (
            <p className="text-sm text-ink-muted">
              Could not read the integration status. The API did not respond.
            </p>
          ) : !status ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : (
            <>
              <StatusRow
                label="API keys"
                ok={status.apiConfigured}
                detail={
                  status.keyIdMasked
                    ? `${status.keyIdMasked} — payment links and subscription reads are real`
                    : "Real calls enabled"
                }
                warning="RAZORPAY_TEST_API_KEY and RAZORPAY_TEST_KEY_SECRET are unset. Every adapter is simulating."
              />
              <StatusRow
                label="Webhook signature"
                ok={status.webhookVerified}
                detail="Inbound webhooks are HMAC-SHA256 verified before processing"
                warning="RAZORPAY_WEBHOOK_SECRET is unset. Unsigned callers are still rejected, but a real Razorpay webhook cannot be verified."
              />

              {status.liveAdapters.length > 0 ? (
                <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-hairline pt-4">
                  <span className="text-[11px] font-medium tracking-[0.06em] text-ink-faint uppercase">
                    Real
                  </span>
                  {status.liveAdapters.map((adapter) => (
                    <Badge key={adapter} className="bg-brand-subtle text-brand">
                      <ShieldCheck aria-hidden />
                      {adapter}
                    </Badge>
                  ))}
                  {/* Named explicitly. A screen that lists what is real without
                      listing what is not invites the reader to assume the rest. */}
                  <span className="text-[11px] font-medium tracking-[0.06em] text-ink-faint uppercase">
                    Simulated
                  </span>
                  {["WhatsApp", "SMS", "Email"].map((channel) => (
                    <Badge key={channel} className="bg-subtle text-ink-faint">
                      {channel}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </>
          )}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-hairline pt-4">
          <Button variant="outline" size="sm" onClick={() => void fireTestWebhook()} disabled={firing}>
            <Zap aria-hidden />
            {firing ? "Firing…" : "Fire a test payment.failed"}
          </Button>
          <p className="text-xs text-ink-faint">
            Posts scenario S3 through the simulator — the same path a real webhook takes, minus the
            signature.
          </p>
        </div>
      </section>

      {/* ---- The mock bank page ---------------------------------------------
          Above the cards, not below, because it is the thing people get wrong
          first and no card number makes sense without it. */}
      <section className="rounded-none border border-info/30 bg-info-subtle p-4">
        <p className="flex items-start gap-2 text-sm leading-relaxed text-info">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>
            <strong className="font-medium">Cards do not decide their own outcome.</strong> After
            entering card details, Razorpay shows a mock bank page with <em>Success</em> and{" "}
            <em>Failure</em> buttons — whichever you click is what happens. The UPI handles below
            are the exception: they resolve on their own.
          </span>
        </p>
      </section>

      {/* ---- Test cards ---------------------------------------------------- */}
      <section className="rounded-none border border-hairline bg-elevated shadow-card">
        <div className="border-b border-hairline p-5">
          <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">
            Test cards
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Any CVV, any future expiry. Published by Razorpay — these are not secrets.
          </p>
        </div>
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {["Network", "Region", "Card number", ""].map((heading, index) => (
                <TableHead
                  key={heading || index}
                  className="px-5 text-[11px] font-medium tracking-[0.06em] text-ink-faint uppercase"
                >
                  {heading}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {TEST_CARDS.map((card) => (
              <TableRow key={card.number} className="border-hairline">
                <TableCell className="px-5 py-3 text-sm font-medium text-ink">
                  {card.network}
                </TableCell>
                <TableCell className="px-5 py-3 text-sm text-ink-muted">{card.region}</TableCell>
                <TableCell className="px-5 py-3 font-mono text-sm text-ink tabular-nums">
                  {card.number}
                </TableCell>
                <TableCell className="px-5 py-3 text-right">
                  <CopyButton
                    value={card.number.replace(/\s/g, "")}
                    label={`${card.network} card number`}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>

      {/* ---- Test UPI ------------------------------------------------------ */}
      <section className="rounded-none border border-hairline bg-elevated p-5 shadow-card">
        <h2 className="font-display text-lg font-semibold tracking-[-0.01em] text-ink">Test UPI</h2>
        <p className="mt-1 text-sm text-ink-muted">
          These resolve without a mock bank page, which makes them the fastest way to demo both
          outcomes.
        </p>
        <ul className="mt-4 space-y-2">
          {TEST_UPI.map((upi) => (
            <li
              key={upi.vpa}
              className="flex items-center justify-between gap-3 rounded-md border border-hairline bg-base px-3 py-2"
            >
              <span className="font-mono text-sm text-ink">{upi.vpa}</span>
              <span className="ml-auto flex items-center gap-2">
                <Badge
                  className={
                    upi.tone === "success"
                      ? "bg-success-subtle text-success"
                      : "bg-danger-subtle text-danger"
                  }
                >
                  {upi.outcome}
                </Badge>
                <CopyButton value={upi.vpa} label={upi.vpa} />
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
