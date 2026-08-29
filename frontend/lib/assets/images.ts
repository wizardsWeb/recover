/**
 * Stock imagery, referenced by URL from the Pexels CDN.
 *
 * Nothing is downloaded into the repository. Pexels serves these with its own
 * caching and resizing, and copying them in would add megabytes to every clone
 * and every container image to save one DNS lookup.
 *
 * **Every entry carries its photographer.** Attribution is not required by the
 * Pexels licence, but a product that quietly presents someone else's work as
 * set dressing is a product that has decided credit is optional. The footer
 * renders these.
 *
 * `width` is requested through the CDN's own query string rather than by
 * shipping a large file and scaling it in CSS — an 800px-wide hero image is
 * roughly a tenth the bytes of the 6000px original nobody can see the detail of.
 */

export interface StockImage {
  /** The CDN URL, already sized. */
  readonly src: string;
  /** Describes the image for a reader who cannot see it. Never decorative-only. */
  readonly alt: string;
  readonly photographer: string;
  readonly photographerUrl: string;
  /** The Pexels page, for anyone checking provenance. */
  readonly source: string;
}

/** Pexels' resize parameters. `auto=compress` picks the format per browser. */
function sized(id: number, slug: string, width: number): string {
  return `https://images.pexels.com/photos/${id}/${slug}.jpeg?auto=compress&cs=tinysrgb&fit=crop&w=${width}`;
}

/**
 * The three playbook scenarios, in the order the landing page tells them.
 *
 * Keyed by playbook so a card cannot drift onto the wrong story — the alternative
 * is a positional array where reordering the cards silently reassigns the
 * pictures.
 */
export const SCENARIO_IMAGES: Record<string, StockImage> = {
  checkout_abandonment: {
    src: sized(36812639, "pexels-photo-36812639", 900),
    alt: "Someone paying on a phone with a card in hand",
    photographer: "Vitaly Gariev",
    photographerUrl: "https://www.pexels.com/@silverkblack",
    source: "https://www.pexels.com/photo/36812639/",
  },
  subscription_failure: {
    src: sized(4308093, "pexels-photo-4308093", 900),
    alt: "Two students working through coursework on a laptop",
    photographer: "Ketut Subiyanto",
    photographerUrl: "https://www.pexels.com/@ketut-subiyanto",
    source: "https://www.pexels.com/photo/4308093/",
  },
  b2b_overdue: {
    src: sized(7581110, "pexels-photo-7581110", 900),
    alt: "A team reviewing figures together in an office",
    photographer: "RDNE Stock project",
    photographerUrl: "https://www.pexels.com/@rdne",
    source: "https://www.pexels.com/photo/7581110/",
  },
};

/** The empty-cases state. A literal declined-payment screen, not a metaphor. */
export const PAYMENT_FAILURE_IMAGE: StockImage = {
  src: sized(7821763, "pexels-photo-7821763", 900),
  alt: "A laptop showing a payment method declined notice",
  photographer: "RDNE Stock project",
  photographerUrl: "https://www.pexels.com/@rdne",
  source: "https://www.pexels.com/photo/7821763/",
};

/** What the auth pages crossfade through. */
export const AUTH_PANEL_IMAGES: readonly StockImage[] = [
  SCENARIO_IMAGES.subscription_failure,
  SCENARIO_IMAGES.checkout_abandonment,
  SCENARIO_IMAGES.b2b_overdue,
];

/**
 * The landing hero's background loop.
 *
 * The brief's asset, re-encoded and served from `public/` rather than hotlinked
 * from its CDN. The original is not web-optimised: its atom order is
 * `ftyp / uuid / free / mdat / moov`, with the 13.8MB `mdat` ahead of the
 * `moov` that describes it. A browser streaming that file cannot read the
 * metadata — and so cannot start playback — until the whole thing has arrived,
 * which behind a full-viewport hero means a black rectangle for the length of
 * the download.
 *
 * The re-encode fixes that and three other things at once:
 *
 *   * `-movflags +faststart` puts `moov` first, so playback starts on the first
 *     few hundred kilobytes instead of the last.
 *   * 1920x1080 at 11Mbps became 1280x720 at CRF 28 — 13.9MB to 455KB, a
 *     thirty-fold cut. It sits behind a 70% scrim, so the detail being thrown
 *     away is detail nobody could resolve.
 *   * There is now a poster: the video's own first frame, 59KB, so the first
 *     paint is the right image rather than black.
 *   * Self-hosted, so the only page a stranger ever sees does not depend on a
 *     third-party CDN staying up.
 *
 * Regenerate with:
 *   ffmpeg -i <source> -an -vf scale=1280:-2 -c:v libx264 -crf 28 -preset slow \
 *     -pix_fmt yuv420p -movflags +faststart public/video/hero-loop.mp4
 *   ffmpeg -i <source> -vf scale=1280:-2 -frames:v 1 -q:v 6 public/video/hero-poster.jpg
 */
export const HERO_VIDEO = {
  src: "/video/hero-loop.mp4",
  poster: "/video/hero-poster.jpg",
  /** Where the footage came from, for anyone re-cutting it. */
  source:
    "https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260809_012548_ef22562c-c0ae-4816-ad9d-f8922af4e6a7.mp4",
} as const;

/** Everything credited in the footer, de-duplicated by photographer. */
export const IMAGE_CREDITS: ReadonlyArray<{ name: string; url: string }> = [
  ...new Map(
    [
      ...Object.values(SCENARIO_IMAGES),
      PAYMENT_FAILURE_IMAGE,
    ].map((asset) => [asset.photographer, { name: asset.photographer, url: asset.photographerUrl }]),
  ).values(),
];
