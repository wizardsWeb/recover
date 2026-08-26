import { Bell, Search } from "lucide-react";

import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { UserMenu } from "@/components/shell/UserMenu";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Button } from "@/components/ui/button";

interface HeaderProps {
  email: string;
  businessName: string;
}

/**
 * Search and notifications are deliberately inert in Phase 1 — the command
 * palette lands with Phase 2, and there is nothing to notify about until the
 * agent runs. Both are rendered so the chrome does not move under the user
 * when they start working.
 */
const NOTIFICATION_COUNT = 0;

export function Header({ email, businessName }: HeaderProps) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-hairline bg-elevated px-6">
      <Breadcrumbs />

      <div className="mx-auto hidden w-full max-w-md md:block">
        <button
          type="button"
          disabled
          className="flex w-full items-center gap-2 rounded-md border border-hairline bg-subtle px-3 py-1.5 text-sm text-ink-faint disabled:cursor-not-allowed"
        >
          <Search className="size-4 shrink-0" aria-hidden />
          <span className="flex-1 text-left">Search cases, customers, IDs…</span>
          <kbd className="rounded-sm border border-hairline bg-elevated px-1.5 py-0.5 font-mono text-[10px] text-ink-faint">
            ⌘K
          </kbd>
        </button>
      </div>

      <div className="ml-auto flex items-center gap-1">
        <Button variant="ghost" size="icon" aria-label="Notifications" className="relative">
          <Bell className="size-4" strokeWidth={1.75} aria-hidden />
          {NOTIFICATION_COUNT > 0 && (
            <span className="absolute top-1.5 right-1.5 size-2 rounded-full bg-brand" aria-hidden />
          )}
        </Button>
        <ThemeToggle />
        <UserMenu email={email} businessName={businessName} />
      </div>
    </header>
  );
}
