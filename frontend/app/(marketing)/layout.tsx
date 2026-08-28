import { Wordmark } from "@/components/brand/Wordmark";
import { IMAGE_CREDITS } from "@/lib/assets/images";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { ButtonLink } from "@/components/ui/button-link";

export default function MarketingLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-dvh flex-col">
      {/* Dark and translucent in both colour modes, so it reads over the hero
          video and over the light section below it without a scroll listener
          deciding which. The same reasoning as the app's rail: chrome is dark,
          content is not, and the boundary never has to be negotiated. */}
      <header className="sticky top-0 z-40 bg-ink-900/80 backdrop-blur-md">
        <nav className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <Wordmark className="text-white" lineClassName="bg-sidebar-gold" />
          <div className="flex items-center gap-1">
            <ThemeToggle className="text-ink-200 hover:bg-white/10 hover:text-white dark:hover:bg-white/10" />
            <ButtonLink
              href="/login"
              variant="ghost"
              size="sm"
              className="text-ink-200 hover:bg-white/10 hover:text-white dark:hover:bg-white/10"
            >
              Log in
            </ButtonLink>
            <ButtonLink href="/signup" size="sm">
              Get started
            </ButtonLink>
          </div>
        </nav>
      </header>

      <main className="flex-1">{children}</main>

      <footer className="border-t border-hairline">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-8 text-sm text-ink-faint sm:flex-row sm:items-center sm:justify-between">
          <p>Recover · Built for Razorpay Buildathon 2026</p>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <a
              href="https://github.com/wizardsWeb/razorpay_buildathon"
              className="transition-colors duration-150 hover:text-ink-muted"
            >
              GitHub
            </a>
            <span>by wizardsWeb</span>
            {/* Attribution is not required by the Pexels licence. It is here
                because a product that quietly uses someone's work as set
                dressing has decided credit is optional. */}
            <span className="text-[11px]">
              Imagery:{" "}
              {IMAGE_CREDITS.map((credit, index) => (
                <span key={credit.name}>
                  {index > 0 && ", "}
                  <a href={credit.url} className="hover:text-ink-muted">
                    {credit.name}
                  </a>
                </span>
              ))}{" "}
              on Pexels
            </span>
          </p>
        </div>
      </footer>
    </div>
  );
}
