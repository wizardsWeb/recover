import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Sora } from "next/font/google";

import { ThemeProvider } from "@/components/theme/ThemeProvider";
import { Toaster } from "@/components/ui/sonner";

import "./globals.css";

// next/font self-hosts these at build time — no request to Google at runtime,
// and no layout shift from a late-arriving face.
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

// Sora carries the display voice: geometric, a little architectural, and not
// the Inter-for-everything that makes every dashboard look like every other
// dashboard. Only the weights actually used are requested — a variable axis
// nobody sets is bytes on every first paint.
const sora = Sora({
  subsets: ["latin"],
  variable: "--font-sora",
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
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
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${sora.variable} ${jetbrainsMono.variable}`}>
      <body className="min-h-dvh bg-base font-body text-ink">
        <ThemeProvider>
          {children}
          <Toaster position="top-right" />
        </ThemeProvider>
      </body>
    </html>
  );
}
