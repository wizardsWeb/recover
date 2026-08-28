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

/** The landing hero's still image — the poster frame behind the video. */
export const HERO_IMAGE: StockImage = {
  src: sized(4307853, "pexels-photo-4307853", 1600),
  alt: "A merchant working at a laptop from home",
  photographer: "Ketut Subiyanto",
  photographerUrl: "https://www.pexels.com/@ketut-subiyanto",
  source: "https://www.pexels.com/photo/4307853/",
};

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
 * Eight seconds, which is short enough that the loop point is not a jump cut
 * and small enough not to dominate the page weight. The 1280px rendition rather
 * than the 1920px one: it sits behind a 75%-opacity scrim at any viewport size,
 * so the extra detail is spent on pixels nobody will ever resolve.
 */
export const HERO_VIDEO = {
  src: "https://videos.pexels.com/video-files/6577159/6577159-hd_1280_720_50fps.mp4",
  /** Shown until the video can play, and instead of it on a slow connection. */
  poster:
    "https://images.pexels.com/videos/6577159/pexels-photo-6577159.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=900&w=1600",
  photographer: "shalender kumar",
  photographerUrl: "https://www.pexels.com/@shalenderkumar",
  source: "https://www.pexels.com/video/6577159/",
} as const;

/** Everything credited in the footer, de-duplicated by photographer. */
export const IMAGE_CREDITS: ReadonlyArray<{ name: string; url: string }> = [
  ...new Map(
    [
      HERO_IMAGE,
      ...Object.values(SCENARIO_IMAGES),
      PAYMENT_FAILURE_IMAGE,
      HERO_VIDEO,
    ].map((asset) => [asset.photographer, { name: asset.photographer, url: asset.photographerUrl }]),
  ).values(),
];
