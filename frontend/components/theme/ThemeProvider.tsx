"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * `attribute="class"` puts `.dark` on <html>, which is what the
 * `@custom-variant dark (&:is(.dark *))` rule in globals.css keys off.
 * next-themes persists the choice in localStorage under `theme`.
 *
 * `TooltipProvider` rides along at the root so any component can render a
 * `Tooltip` without shipping its own provider. That is not just convenience:
 * the provider owns the shared open/close delay, and a page with four local
 * providers has four independent hover timers — so moving the pointer from one
 * tooltip to the next re-pays the full delay each time instead of opening
 * immediately, which is the behaviour that makes a row of them feel broken.
 *
 * 250ms rather than the component default of 0. A tooltip that appears the
 * instant the pointer crosses an element fires constantly while the reader is
 * simply moving across the page.
 */
export function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      {...props}
    >
      <TooltipProvider delay={250}>{children}</TooltipProvider>
    </NextThemesProvider>
  );
}
