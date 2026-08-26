"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

/**
 * `attribute="class"` puts `.dark` on <html>, which is what the
 * `@custom-variant dark (&:is(.dark *))` rule in globals.css keys off.
 * next-themes persists the choice in localStorage under `theme`.
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
      {children}
    </NextThemesProvider>
  );
}
