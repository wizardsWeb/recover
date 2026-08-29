import { request } from "@/lib/api/client";

/**
 * Whether the Razorpay integration is wired, as the server sees it.
 *
 * Every field here is a *description* of configuration, never configuration
 * itself — the backend has no route that returns a secret, and this type is the
 * shape of that decision. `keyIdMasked` is the public key id with all but its
 * last four characters replaced.
 */
export interface RazorpayStatus {
  /** Whether outbound API calls are possible at all. */
  apiConfigured: boolean;
  /**
   * Whether inbound webhooks are signature-verified.
   *
   * `false` means the endpoint accepts anything that reaches it. Surfaced rather
   * than hidden: a publicly reachable webhook with no secret is the one
   * configuration mistake that lets a stranger close cases as recovered.
   */
  webhookVerified: boolean;
  /** `test`, `live`, or `unconfigured`, read from the key's own prefix. */
  mode: "test" | "live" | "unconfigured";
  /** `rzp_test_••••1234`, or an empty string. */
  keyIdMasked: string;
  /** Which adapters make real calls. Messaging is never in this list. */
  liveAdapters: string[];
}

export function fetchRazorpayStatus(): Promise<RazorpayStatus> {
  return request<RazorpayStatus>("/api/integrations/razorpay");
}
