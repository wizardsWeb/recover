import Link from "next/link";

import { AuthPanel } from "@/components/auth/AuthPanel";

/**
 * Sign-in, sign-up and onboarding: form on one side, one plate on the other.
 *
 * The form is centred on both axes of the column it occupies, and the column is
 * the whole page until `lg`. That last part is the fix for a real bug: the plate
 * is `hidden lg:block`, so below that breakpoint the grid collapses to one
 * column — and the form, left-aligned inside it with a 26rem cap, sat stranded
 * against the left edge of a wide empty page. Centring is not decoration here,
 * it is what makes the layout survive the panel being absent.
 *
 * `ground-light` because these are public pages with a decided ground, like the
 * landing page, and there is no theme toggle on any of them.
 *
 * The wordmark is absolutely positioned rather than a flex row above the form.
 * In flow it would push the form off centre by its own height, and the form
 * being exactly centred matters more than the wordmark participating in the
 * column's vertical rhythm.
 */
export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="ground-light relative min-h-dvh bg-paper text-ink lg:grid lg:grid-cols-2">
      <Link
        href="/"
        className="absolute top-6 left-6 z-10 text-[13px] leading-[1.15] sm:top-8 sm:left-10"
      >
        <span className="block">Recover</span>
        <span className="block text-ink-muted">Revenue Recovery</span>
        <span className="block text-ink-muted">for Razorpay</span>
      </Link>

      {/* The vertical padding clears the wordmark rather than letting the form
          slide under it — the wordmark is out of flow, so nothing else reserves
          that space. 6rem is the smallest value that does: the mark sits at
          1.5rem with about 3rem of its own height. */}
      <main className="flex min-h-dvh items-center justify-center px-6 py-24 sm:px-10 sm:py-28 lg:min-h-0">
        <div className="w-full max-w-[24rem]">{children}</div>
      </main>

      <AuthPanel />
    </div>
  );
}
