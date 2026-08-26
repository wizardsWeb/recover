"use client";

import { PanelLeftClose, PanelLeftOpen, Terminal } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Wordmark } from "@/components/brand/Wordmark";
import { NAV_ITEMS, isActive } from "@/components/shell/nav";
import { cn } from "@/lib/utils/cn";

export const SIDEBAR_COOKIE = "recover_sidebar_collapsed";

/** A year — the preference should outlive the session that set it. */
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

interface SidebarProps {
  /** Dev-only tools are hidden outside local development. */
  showDevTools: boolean;
  /** Read from the cookie by the layout, so the server renders the right width. */
  defaultCollapsed: boolean;
}

export function Sidebar({ showDevTools, defaultCollapsed }: SidebarProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  function toggle() {
    setCollapsed((previous) => {
      const next = !previous;
      // A cookie rather than localStorage: the server layout can read it, so
      // the sidebar renders at the right width in the very first HTML instead
      // of flashing open and snapping shut after hydration.
      document.cookie = `${SIDEBAR_COOKIE}=${next}; path=/; max-age=${COOKIE_MAX_AGE}; samesite=lax`;
      return next;
    });
  }

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-r border-hairline bg-elevated transition-[width] duration-200",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <div className={cn("flex h-14 items-center border-b border-hairline", collapsed ? "justify-center px-2" : "px-5")}>
        {collapsed ? (
          <Link href="/app" aria-label="Recover — dashboard" className="font-display text-lg font-semibold text-brand">
            R
          </Link>
        ) : (
          <Wordmark href="/app" size="sm" />
        )}
      </div>

      <nav className="flex-1 space-y-0.5 p-2" aria-label="Main">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              title={collapsed ? label : undefined}
              className={cn(
                // The 2px left rule is drawn as a transparent border on every
                // item so the label never shifts when the active one gains it.
                "flex items-center gap-3 rounded-md border-l-2 border-transparent px-3 py-2 text-sm transition-colors",
                collapsed && "justify-center px-0",
                active
                  ? "border-l-brand bg-brand-subtle font-medium text-brand"
                  : "text-ink-muted hover:bg-subtle hover:text-ink",
              )}
            >
              <Icon className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          );
        })}
      </nav>

      {showDevTools && (
        <div className="border-t border-hairline p-2">
          {!collapsed && (
            <p className="px-3 pt-1 pb-2 text-[11px] font-medium tracking-[0.1em] text-ink-faint uppercase">
              Development
            </p>
          )}
          <Link
            href="/dev/simulator"
            title={collapsed ? "Simulator" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-ink-muted transition-colors hover:bg-subtle hover:text-ink",
              collapsed && "justify-center px-0",
            )}
          >
            <Terminal className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
            {!collapsed && <span>Simulator</span>}
          </Link>
        </div>
      )}

      <div className="border-t border-hairline p-2">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-ink-faint transition-colors hover:bg-subtle hover:text-ink",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
          ) : (
            <PanelLeftClose className="size-4 shrink-0" strokeWidth={1.75} aria-hidden />
          )}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
