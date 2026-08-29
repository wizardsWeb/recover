import Link from "next/link";

import { AuthPanel } from "@/components/auth/AuthPanel";

/**
 * Sign-in, sign-up and onboarding: form on the left, one plate on the right.
 *
 * `ground-light` for the same reason the landing page has it — these are public
 * pages with a decided ground, and there is no theme toggle here either. A
 * reader arriving from the landing page should not find a different product.
 *
 * The wordmark is the same three lines as the landing chrome, and it is the only
 * chrome: no header bar, no rule under it, nothing to separate it from the form
 * below. The split itself is the structure.
 */
export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="ground-light grid min-h-dvh bg-paper text-ink lg:grid-cols-2">
      <div className="flex flex-col px-5 sm:px-7">
        <div className="pt-4 text-[13px] leading-[1.15]">
          <Link href="/" className="block">
            <span className="block">Recover</span>
            <span className="block text-ink-muted">Revenue Recovery</span>
            <span className="block text-ink-muted">for Razorpay</span>
          </Link>
        </div>

        {/* The form sits at the optical centre of its column rather than the
            geometric one — `pb-24` pulls it up, because a form centred against
            a tall viewport reads as sitting low. */}
        <main className="flex flex-1 items-center pb-24">
          <div className="w-full max-w-[26rem]">{children}</div>
        </main>
      </div>

      <AuthPanel />
    </div>
  );
}
