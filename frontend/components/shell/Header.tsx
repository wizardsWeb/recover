import { Bell } from "lucide-react";

import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { CommandPalette } from "@/components/shell/CommandPalette";
import { UserMenu } from "@/components/shell/UserMenu";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Button } from "@/components/ui/button";
import { isProduction } from "@/lib/env";

interface HeaderProps {
  email: string;
  businessName: string;
}

/**
 * The header sits on `bg-base`, the page surface, rather than on `bg-elevated`.
 * A white bar above an off-white page draws a line the content does not need;
 * matching the surface lets the single hairline underneath do that job alone.
 *
 * Notifications are still inert — there is nothing to notify about until the
 * agent runs — but the bell is rendered so the chrome does not move under the
 * user later. Search is live: the box is the CommandPalette's own trigger, so
 * this stays a server component and only the palette ships to the client.
 */
const NOTIFICATION_COUNT = 0;

export function Header({ email, businessName }: HeaderProps) {
  return (
    <header className="flex h-[52px] shrink-0 items-center gap-4 border-b border-hairline bg-base px-6 print:hidden">
      <Breadcrumbs />

      <div className="mx-auto hidden w-full max-w-md md:block">
        <CommandPalette />
      </div>

      <div className="ml-auto flex items-center gap-1">
        {/* Which deployment am I looking at? Worth answering at a glance when a
            local build, a local-prod container, and the live site all look
            identical. Deliberately quiet — it is a wayfinding cue, not a
            warning. It sits in the control cluster rather than pinned to the
            header's bottom-right corner, where a 56px-tall bar would put it
            underneath the avatar. */}
        {isProduction && (
          <span
            title="You are on the production deployment"
            className="mr-2 hidden rounded-full border border-hairline bg-subtle px-2 py-0.5 font-mono text-[10px] tracking-wider text-ink-faint uppercase sm:inline-block"
          >
            production
          </span>
        )}
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
