"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { FlaskConical, PanelLeftClose, PanelLeftOpen, Settings } from "lucide-react";

import { NAV_ITEMS, isActive } from "@/components/shell/nav";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { PersonAvatar } from "@/components/ui/PersonAvatar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { HOVER_NUDGE, SPRING_NUDGE } from "@/lib/motion";
import { cn } from "@/lib/utils/cn";

export const SIDEBAR_COOKIE = "recover_sidebar_collapsed";

/** A year — the preference should outlive the session that set it. */
const COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

/**
 * `Link` with Framer Motion's props bolted on.
 *
 * Created once at module scope rather than inside the component. `motion.create`
 * builds a new component type on every call, and a new type on every render is
 * a full unmount/remount of every nav item each time the route changes — which
 * would drop the hover state mid-gesture.
 */
const MotionLink = motion.create(Link);

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
 *
 * The hover nudge is a spring rather than a CSS transition because 3px is a
 * distance a linear ease makes look like a glitch — it arrives and stops. A
 * stiff spring gives it the small overshoot that reads as a physical nudge.
 */
export function Sidebar({ showDevTools, defaultCollapsed, businessName, email }: SidebarProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const prefersReducedMotion = useReducedMotion();

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
        "flex shrink-0 flex-col bg-sidebar-bg transition-[width] duration-200 ease-out print:hidden",
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
            // The label is a `Tooltip` rather than a `title`, and only on the
            // collapsed rail — when the label is visible beside the icon a
            // tooltip repeating it is noise. `aria-label` carries the
            // accessible name in both states, because the visible label is
            // hidden by a media query rather than removed from the DOM, and a
            // tooltip is not an accessible name.
            <Tooltip key={href}>
              <TooltipTrigger
                render={
                  <MotionLink
                    href={href}
                    aria-label={label}
                    aria-current={active ? "page" : undefined}
                    // No nudge on the icon-only rail: a 3px shift inside a 64px
                    // column moves the icon off its own optical centre, which
                    // reads as misalignment rather than as feedback.
                    whileHover={prefersReducedMotion || collapsed ? undefined : HOVER_NUDGE}
                    transition={SPRING_NUDGE}
                    className={cn(
                      // The 3px left rule is drawn as a transparent border on
                      // every item so the label never shifts when the active
                      // one gains it.
                      "group flex items-center gap-3 rounded-md border-l-[3px] border-transparent py-2 text-sm",
                      "transition-[background-color,color] duration-150 ease-out",
                      collapsed
                        ? "justify-center px-0"
                        : "justify-center px-0 lg:justify-start lg:px-3",
                      active
                        ? "border-l-brand bg-sidebar-active font-medium text-sidebar-fg"
                        : "text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-fg",
                    )}
                  />
                }
              >
                <Icon className="size-[18px] shrink-0" strokeWidth={1.5} aria-hidden />
                {!collapsed && (
                  <span aria-hidden className="hidden truncate lg:inline">
                    {label}
                  </span>
                )}
              </TooltipTrigger>
              {collapsed ? <TooltipContent side="right">{label}</TooltipContent> : null}
            </Tooltip>
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
          <Tooltip>
            <TooltipTrigger
              render={
                <MotionLink
                  href="/app/dev/simulator"
                  aria-label="Simulator"
                  whileHover={prefersReducedMotion || collapsed ? undefined : HOVER_NUDGE}
                  transition={SPRING_NUDGE}
                  className={cn(
                    "flex items-center gap-3 rounded-md py-2 text-sm text-sidebar-muted transition-colors duration-150 hover:bg-sidebar-hover hover:text-sidebar-fg",
                    collapsed
                      ? "justify-center px-0"
                      : "justify-center px-0 lg:justify-start lg:px-3",
                  )}
                />
              }
            >
              <FlaskConical className="size-[18px] shrink-0" strokeWidth={1.5} aria-hidden />
              {!collapsed && (
                <span aria-hidden className="hidden lg:inline">
                  Simulator
                </span>
              )}
            </TooltipTrigger>
            {collapsed ? <TooltipContent side="right">Simulator</TooltipContent> : null}
          </Tooltip>
        </div>
      )}

      {/* ---- Who is signed in ----------------------------------------------
          Identity lives at the bottom of the rail and the *menu* lives in the
          header. Not a duplicate: this answers "whose data am I looking at",
          which is worth a permanent answer on a product where the reply is a
          business rather than a person.

          The avatar is seeded on the email rather than the business name, so
          renaming the business does not change the merchant's own face. */}
      <div className="mt-2 border-t border-sidebar-border p-2">
        <div
          className={cn(
            "flex items-center gap-2.5 rounded-md px-2 py-2",
            collapsed && "justify-center px-0",
          )}
        >
          <PersonAvatar
            seed={email || businessName}
            name={businessName}
            className="size-7 shrink-0"
          />
          {!collapsed && (
            <>
              <span className="hidden min-w-0 flex-1 lg:block">
                <span className="block truncate text-xs font-medium text-sidebar-fg">
                  {businessName}
                </span>
                <span className="block truncate font-mono text-[11px] text-sidebar-muted">
                  {email}
                </span>
              </span>
              <div className="hidden shrink-0 items-center lg:flex">
                <ThemeToggle className="size-7 text-sidebar-muted hover:bg-sidebar-active hover:text-sidebar-fg dark:hover:bg-sidebar-active" />
                <Link
                  href="/app/settings"
                  aria-label="Settings"
                  className="rounded-md p-1.5 text-sidebar-muted transition-colors duration-150 hover:bg-sidebar-active hover:text-sidebar-fg"
                >
                  <Settings className="size-4" strokeWidth={1.5} aria-hidden />
                </Link>
              </div>
            </>
          )}
        </div>

        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "hidden w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-muted transition-colors duration-150 hover:bg-sidebar-hover hover:text-sidebar-fg lg:flex",
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
