"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { FlaskConical, PanelLeftClose, PanelLeftOpen, Settings } from "lucide-react";

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
  businessName: string;
  email: string;
}

/**
 * The navigation rail — dark in both colour modes.
 *
 * That is a navigational decision rather than a stylistic one. A rail that
 * inverts with the theme is a second content surface competing with the page;
 * one that stays dark reads as chrome, so the eye stops treating it as
 * something to look at and goes where the work is. Razorpay, Linear and Vercel
 * all land in the same place.
 *
 * Its colours therefore come from `--sidebar-*` rather than from the surface
 * tokens, which is what keeps the light-mode swap from reaching in here.
 *
 * Icons are drawn at `strokeWidth={1.5}` rather than Lucide's default 2. At
 * 18px on a dark ground the default reads as heavy and slightly crude; a
 * thinner stroke is the difference between an icon set and a toolbar.
 */
export function Sidebar({ showDevTools, defaultCollapsed, businessName, email }: SidebarProps) {
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

  const initials = businessName.trim().slice(0, 2).toUpperCase() || "RC";

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col bg-sidebar-bg transition-[width] duration-200 print:hidden",
        // Below `lg` the rail is icon-only whatever the stored preference says.
        // Done in CSS rather than by measuring the viewport in JS: a media
        // query cannot be read during SSR, so a JS version renders the wide
        // sidebar first and snaps narrow after hydration.
        collapsed ? "w-16" : "w-16 lg:w-60",
      )}
    >
      {/* ---- Wordmark ------------------------------------------------------
          The one place the rupee glyph appears in the chrome. It is the mark,
          not decoration — which is why it does not also appear beside every
          number in the tables underneath. */}
      <div
        className={cn(
          "flex h-14 items-center",
          collapsed ? "justify-center px-2" : "justify-center px-2 lg:justify-start lg:px-5",
        )}
      >
        <Link
          href="/app"
          aria-label="Recover — dashboard"
          className="flex items-center gap-1.5 transition-opacity hover:opacity-80"
        >
          <span aria-hidden className="font-display text-lg leading-none text-sidebar-gold">
            ₹
          </span>
          {!collapsed && (
            <span className="hidden font-display text-base font-semibold tracking-[-0.02em] text-sidebar-fg lg:inline">
              Recover
            </span>
          )}
        </Link>
      </div>

      <nav className="flex-1 space-y-0.5 px-2 pt-2" aria-label="Main">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
          const active = isActive(pathname, href);
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              title={collapsed ? label : undefined}
              className={cn(
                // The 3px left rule is drawn as a transparent border on every
                // item so the label never shifts when the active one gains it.
                "group flex items-center gap-3 rounded-md border-l-[3px] border-transparent py-2 text-sm",
                "transition-[background-color,color,transform] duration-150 ease-out",
                collapsed ? "justify-center px-0" : "justify-center px-0 lg:justify-start lg:px-3",
                active
                  ? "border-l-rupee bg-sidebar-active font-medium text-sidebar-fg"
                  : "text-sidebar-muted hover:bg-sidebar-active/60 hover:text-sidebar-fg lg:hover:translate-x-0.5",
              )}
            >
              <Icon className="size-[18px] shrink-0" strokeWidth={1.5} aria-hidden />
              {!collapsed && <span className="hidden truncate lg:inline">{label}</span>}
            </Link>
          );
        })}
      </nav>

      {showDevTools && (
        <div className="mx-2 border-t border-sidebar-border pt-2">
          {!collapsed && (
            <p className="hidden px-3 pt-1 pb-2 text-[10px] font-medium tracking-[0.12em] text-sidebar-muted uppercase lg:block">
              Development
            </p>
          )}
          <Link
            href="/app/dev/simulator"
            title={collapsed ? "Simulator" : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md py-2 text-sm text-sidebar-muted transition-colors duration-150 hover:bg-sidebar-active/60 hover:text-sidebar-fg",
              collapsed ? "justify-center px-0" : "justify-center px-0 lg:justify-start lg:px-3",
            )}
          >
            <FlaskConical className="size-[18px] shrink-0" strokeWidth={1.5} aria-hidden />
            {!collapsed && <span className="hidden lg:inline">Simulator</span>}
          </Link>
        </div>
      )}

      {/* ---- Who is signed in ----------------------------------------------
          Identity lives at the bottom of the rail and the *menu* lives in the
          header. Not a duplicate: this answers "whose data am I looking at",
          which is worth a permanent answer on a product where the reply is a
          business rather than a person. */}
      <div className="mt-2 border-t border-sidebar-border p-2">
        <div
          className={cn(
            "flex items-center gap-2.5 rounded-md px-2 py-2",
            collapsed && "justify-center px-0",
          )}
        >
          <span
            aria-hidden
            className="flex size-7 shrink-0 items-center justify-center rounded-full bg-sidebar-active text-[11px] font-medium text-sidebar-fg"
          >
            {initials}
          </span>
          {!collapsed && (
            <>
              <span className="hidden min-w-0 flex-1 lg:block">
                <span className="block truncate text-xs font-medium text-sidebar-fg">
                  {businessName}
                </span>
                <span className="block truncate text-[11px] text-sidebar-muted">{email}</span>
              </span>
              <Link
                href="/app/settings"
                aria-label="Settings"
                className="hidden shrink-0 rounded-md p-1 text-sidebar-muted transition-colors duration-150 hover:bg-sidebar-active hover:text-sidebar-fg lg:block"
              >
                <Settings className="size-4" strokeWidth={1.5} aria-hidden />
              </Link>
            </>
          )}
        </div>

        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "hidden w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-muted transition-colors duration-150 hover:bg-sidebar-active/60 hover:text-sidebar-fg lg:flex",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="size-[18px] shrink-0" strokeWidth={1.5} aria-hidden />
          ) : (
            <PanelLeftClose className="size-[18px] shrink-0" strokeWidth={1.5} aria-hidden />
          )}
          {!collapsed && <span className="text-xs">Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
