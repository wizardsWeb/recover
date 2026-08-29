import { AuthPanel } from "@/components/auth/AuthPanel";
import { Wordmark } from "@/components/brand/Wordmark";
import { ThemeToggle } from "@/components/theme/ThemeToggle";

/**
 * Sign-in, sign-up and onboarding: form on the left, context on the right.
 *
 * The split collapses below `lg` and the panel is dropped rather than stacked.
 * A photograph above a login form on a phone pushes the password field below
 * the fold to show a picture nobody came for.
 */
export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <div className="flex flex-col bg-base">
        <header className="flex h-14 items-center justify-between px-6">
          <Wordmark />
          <ThemeToggle />
        </header>

        <main className="flex flex-1 items-center justify-center px-6 pb-20">
          <div className="w-full max-w-sm">{children}</div>
        </main>
      </div>

      <AuthPanel />
    </div>
  );
}
