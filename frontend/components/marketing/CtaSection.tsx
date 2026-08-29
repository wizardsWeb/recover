import Link from "next/link";

/**
 * Section six: the ask.
 *
 * Two buttons, and the second one is deliberately quieter. A page that offers
 * two equally-weighted actions has not decided what it wants, and the reader
 * has to. The white pill is the ask; the outlined one is for the reader who was
 * never going to sign up before reading the source.
 */
export function CtaSection() {
  return (
    <section id="start" className="scroll-mt-24 bg-ink-900 py-24 text-center sm:py-32">
      <div className="mx-auto max-w-2xl px-6">
        <h2 className="font-display text-4xl leading-[1.1] font-bold tracking-[-0.03em] text-white sm:text-5xl">
          Start recovering today.
        </h2>
        <p className="mt-4 text-lg text-white/50">Built for Razorpay merchants. Free to try.</p>

        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/signup"
            className="rounded-full bg-white px-6 py-3 text-sm font-semibold text-ink-900 transition-transform duration-150 ease-out hover:-translate-y-0.5 focus-visible:ring-3 focus-visible:ring-white/50 focus-visible:outline-none motion-reduce:transition-none motion-reduce:hover:translate-y-0"
          >
            Get started
          </Link>
          <a
            href="https://github.com/wizardsWeb/razorpay_buildathon"
            className="rounded-full border border-white/30 px-6 py-3 text-sm font-semibold text-white transition-colors duration-150 hover:bg-white/10 focus-visible:ring-3 focus-visible:ring-white/50 focus-visible:outline-none"
          >
            View on GitHub
          </a>
        </div>
      </div>
    </section>
  );
}
