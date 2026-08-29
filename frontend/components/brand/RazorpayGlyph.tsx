import { cn } from "@/lib/utils/cn";

/**
 * Razorpay's glyph, inlined.
 *
 * The path data is their published mark from `razorpay.com/assets/razorpay-glyph.svg`
 * — 255 bytes, which is less than the HTTP headers of a request to fetch it.
 * Inlining also means it scales with `currentColor`-adjacent sizing, survives an
 * offline demo, and does not put razorpay.com in the critical path of our own
 * dashboard.
 *
 * The two fills are Razorpay's brand colours and are deliberately *not* themed.
 * Every other colour in this product re-tints between light and dark; a
 * vendor's mark rendered in a colour they do not use is worse than no mark, so
 * these two tokens hold the same value in both modes.
 *
 * `aria-hidden` by default: the mark almost always sits next to the word
 * "Razorpay", and a screen reader announcing "Razorpay Razorpay" is noise. Pass
 * a `title` where it stands alone.
 */
export function RazorpayGlyph({
  className,
  title,
}: {
  className?: string;
  title?: string;
}) {
  return (
    <svg
      viewBox="0 0 640 640"
      className={cn("size-4 shrink-0", className)}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <g fill="none" fillRule="evenodd">
        <path
          fill="var(--razorpay-blue)"
          d="M299.6 262.7l-15.7 58 90-58.3-59 220h60l87-325"
        />
        <path fill="var(--razorpay-navy)" d="M202.6 390l-24.8 92.4h122.7l50.2-188-148 95.5" />
      </g>
    </svg>
  );
}

/**
 * The glyph plus the word, as one unit.
 *
 * Used wherever the point is attribution rather than decoration — the sidebar
 * footer, the landing rails strip. On a dark ground the navy half of the glyph
 * disappears, so `onDark` lifts it to white; the blue half reads on both.
 */
export function RazorpayWordmark({
  className,
  onDark = false,
}: {
  className?: string;
  onDark?: boolean;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <RazorpayGlyph
        className={cn("size-3.5", onDark && "[&>g>path:last-child]:fill-white")}
        title="Razorpay"
      />
      <span className={cn("font-medium", onDark ? "text-white/70" : "text-ink-muted")}>
        Razorpay
      </span>
    </span>
  );
}
