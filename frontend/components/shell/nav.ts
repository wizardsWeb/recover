import {
  FileSearch,
  FolderOpen,
  LayoutDashboard,
  ListChecks,
  PlaySquare,
  RadioTower,
  Settings,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

/**
 * The single source of truth for in-app navigation: the sidebar renders it, and
 * the header derives breadcrumbs from it. Adding a section in one place is what
 * keeps the two from disagreeing.
 */
export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/app", label: "Dashboard", icon: LayoutDashboard },
  { href: "/app/cases", label: "Cases", icon: FolderOpen },
  { href: "/app/playbooks", label: "Playbooks", icon: ListChecks },
  { href: "/app/network", label: "Network", icon: RadioTower },
  { href: "/app/roi", label: "ROI", icon: TrendingUp },
  { href: "/app/audit", label: "Audit", icon: FileSearch },
  { href: "/app/batch", label: "Batch", icon: PlaySquare },
  { href: "/app/settings", label: "Settings", icon: Settings },
];

/**
 * Whether `href` is the section the user is currently in.
 *
 * `/app` is special-cased: as a prefix it matches every other section, so it
 * only counts when the path is exactly `/app`.
 */
export function isActive(pathname: string, href: string): boolean {
  if (href === "/app") return pathname === "/app";
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Breadcrumb trail for a path: always Dashboard, plus the section if deeper. */
export function breadcrumbsFor(pathname: string): NavItem[] {
  const root = NAV_ITEMS[0];
  if (pathname === "/app") return [root];

  const section = NAV_ITEMS.slice(1).find((item) => isActive(pathname, item.href));
  return section ? [root, section] : [root];
}
