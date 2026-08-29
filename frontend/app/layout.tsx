import type { Metadata } from "next";
import { Instrument_Serif, Inter_Tight, JetBrains_Mono } from "next/font/google";

import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

/**
 * Three faces, and between them exactly one weight.
 *
 * Inter Tight rather than Inter: display type here is set at -0.03em with a
 * line-height under 0.8, and Inter's default sidebearings fight that — letters
 * stay visibly apart at sizes where they should almost touch. Inter Tight is
 * drawn for it.
 *
 * Instrument Serif is the counterpoint, and it works at both ends of the scale:
 * a 96px statement paragraph and a 13px meta label. High contrast, and no bold
 * cut exists — which is the constraint this system wants anyway.
 *
 * JetBrains Mono stays for figures, case ids and timestamps. It is the only one
 * of the three here for a reason other than voice: money in a column has to line
 * up, and a ledger is this product's actual subject.
 *
 * **Weight 400 only, all three.** Nothing else is requested, so nothing else can
 * be used by accident — a stray `font-bold` cannot render bold when the bold cut
 * was never downloaded. `globals.css` collapses the weight utilities to match,
 * so the two enforce the same rule from both ends.
 */
const interTight = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-inter-tight",
  weight: ["400"],
  display: "swap",
});

const instrumentSerif = Instrument_Serif({
  subsets: ["latin"],
  variable: "--font-instrument-serif",
  weight: ["400"],
  style: ["normal", "italic"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  weight: ["400"],
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Recover — AI revenue recovery for Razorpay merchants",
    template: "%s · Recover",
  },
  description:
    "Recover finds revenue slipping away — failed payments, dropped carts, broken subscriptions, overdue invoices — and wins it back.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // suppressHydrationWarning: next-themes writes the theme class onto <html>
    // before React hydrates, so the server and client markup differ by design.
    <html lang="en" suppressHydrationWarning className={`${interTight.variable} ${instrumentSerif.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-dvh bg-base font-sans text-ink">
        <ThemeProvider>
          {children}
          <Toaster position="top-right" />
        </ThemeProvider>
      </body>
    </html>
  );
}
