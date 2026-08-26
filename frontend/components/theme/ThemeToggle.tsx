"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

const ORDER = ["light", "dark", "system"] as const;
type Theme = (typeof ORDER)[number];

const ICONS: Record<Theme, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
};

const LABELS: Record<Theme, string> = {
  light: "Light theme",
  dark: "Dark theme",
  system: "System theme",
};

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  // The server has no idea which theme the browser will resolve to, so the icon
  // is held back until after hydration rather than flashing the wrong one.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  const current: Theme = mounted && ORDER.includes(theme as Theme) ? (theme as Theme) : "system";
  const Icon = ICONS[current];

  function cycle() {
    const next = ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
    setTheme(next);
  }

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={cycle}
      aria-label={`${LABELS[current]}. Click to change.`}
      title={LABELS[current]}
    >
      {mounted ? <Icon className="size-4" aria-hidden /> : <span className="size-4" />}
    </Button>
  );
}
