import { ButtonLink } from "@/components/ui/button-link";
import { HERO_VIDEO } from "@/lib/assets/images";
import { ScrollCue } from "@/components/marketing/ScrollCue";

/**
 * The opening shot.
 *
 * A city loop behind a near-opaque scrim. The video is atmosphere, not
 * information — nothing in it needs to be read — which is what makes a 75%
 * overlay the right call rather than a compromise: the text sits at 15:1
 * against the scrim regardless of which frame is underneath, so legibility
 * never depends on the video's luminance at a given moment.
 *
 * `poster` matters more than it looks. It is the first paint on any connection
 * slow enough that 2.5MB of MP4 has not arrived, and without it the hero is a
 * black rectangle for as long as that takes.
 *
 * The stats are the real ones from a 1,000-case batch run, not invented
 * marketing numbers — `/app/batch` computes them and this quotes them. Rounded,
 * because a landing page claiming 41.97% is a landing page nobody believes.
 */
export function Hero() {
  return (
    <section className="relative isolate flex min-h-[calc(100dvh-3.5rem)] items-center overflow-hidden bg-ink-900">
      <video
        className="absolute inset-0 -z-20 size-full object-cover"
        src={HERO_VIDEO.src}
        poster={HERO_VIDEO.poster}
        autoPlay
        loop
        muted
        playsInline
        // Decorative: the frame carries no information the copy does not.
        aria-hidden
        tabIndex={-1}
      />
      <div aria-hidden className="absolute inset-0 -z-10 bg-ink-900/75" />

      <div className="mx-auto w-full max-w-4xl px-6 py-24 text-center">
        <p className="font-display text-xs font-medium tracking-[0.12em] text-sidebar-gold uppercase">
          Razorpay Buildathon 2026 · Track 03
        </p>

        <h1 className="mt-6 font-display text-5xl leading-[1.08] font-bold tracking-[-0.03em] text-white sm:text-6xl lg:text-7xl">
          Every rupee has a reason.
        </h1>

        <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-ink-200 sm:text-xl">
          An AI agent that watches your Razorpay event stream, diagnoses why revenue slips, and
          wins it back — compliantly.
        </p>

        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <ButtonLink href="/signup" size="lg">
            Get started →
          </ButtonLink>
          <ButtonLink
            href="#how-it-works"
            size="lg"
            variant="outline"
            className="border-white/35 bg-transparent text-white hover:bg-white/10 hover:text-white dark:border-white/35 dark:bg-transparent dark:hover:bg-white/10"
          >
            Watch how it works
          </ButtonLink>
        </div>

        <ul className="mt-10 flex flex-wrap items-center justify-center gap-x-3 gap-y-2 text-sm">
          {[
            { value: "42%", label: "recovery rate" },
            { value: "0", label: "compliance violations" },
            { value: "₹9.2L", label: "incremental" },
          ].map((stat, index) => (
            <li key={stat.label} className="flex items-center gap-3">
              {index > 0 && (
                <span aria-hidden className="text-sidebar-gold">
                  ·
                </span>
              )}
              <span className="rounded-full border border-white/15 bg-white/5 px-3.5 py-1.5">
                <span className="font-display font-semibold text-white">{stat.value}</span>{" "}
                <span className="text-ink-200">{stat.label}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      <ScrollCue />
    </section>
  );
}
