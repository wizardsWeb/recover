import { LandingNav } from "@/components/marketing/LandingNav";
import { IMAGE_CREDITS } from "@/lib/assets/images";

export default function MarketingLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-dvh flex-col">
      {/* Fixed rather than sticky, and outside `main`: it floats over the hero
          video from the first frame instead of being a bar the page pushes
          down. */}
      <LandingNav />

      <main className="flex-1">{children}</main>

      <footer className="bg-ink-900">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-8 text-sm text-white/40 sm:flex-row sm:items-center sm:justify-between">
          <p>Recover · Built for Razorpay Buildathon 2026 · wizardsWeb</p>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <a
              href="https://github.com/wizardsWeb/razorpay_buildathon"
              className="transition-colors duration-150 hover:text-white/70"
            >
              GitHub
            </a>
            {/* Attribution is not required by the Pexels licence. It is here
                because a product that quietly uses someone's work as set
                dressing has decided credit is optional. The font's licence,
                unlike Pexels', does require it. */}
            <span className="text-[11px]">
              Imagery:{" "}
              {IMAGE_CREDITS.map((credit, index) => (
                <span key={credit.name}>
                  {index > 0 && ", "}
                  <a href={credit.url} className="hover:text-white/70">
                    {credit.name}
                  </a>
                </span>
              ))}{" "}
              on Pexels · Headline face from{" "}
              <a href="https://www.onlinewebfonts.com/fonts" className="hover:text-white/70">
                Web Fonts
              </a>
              , CC BY 4.0
            </span>
          </p>
        </div>
      </footer>
    </div>
  );
}
