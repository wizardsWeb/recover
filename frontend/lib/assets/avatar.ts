/**
 * Generated avatars, from DiceBear's HTTP API.
 *
 * The people in this product are seeded demo customers — there are no uploaded
 * profile pictures and there never will be. The options are a coloured initial,
 * a grey silhouette, or a deterministic generated face, and the generated face
 * is the only one that makes a table of twenty customers scannable: the eye
 * finds "the one with the green hair" several fixations before it finds "MS".
 *
 * Deterministic on the seed, which is why the seed is the customer's id rather
 * than their name — a merchant renaming a contact should not hand them a
 * different face.
 *
 * Served as SVG and rendered through a plain `<img>` (base-ui's `AvatarImage`),
 * not `next/image`. Routing a 1KB SVG through the image optimiser would cost a
 * round trip to our own server to save nothing, and would need
 * `dangerouslyAllowSVG` — which turns the optimiser into an open proxy for
 * arbitrary SVG — to do it.
 */

const BASE = "https://api.dicebear.com/9.x";

/**
 * `notionists-neutral` for people, `shapes` for anything that is not a person.
 *
 * Neutral, because the variants with backgrounds fight the table row they sit
 * in. The palette below is the ledger's own ink tints rather than DiceBear's
 * default primaries, so twenty avatars in a column read as one product instead
 * of as a bag of stickers.
 */
export type AvatarStyle = "notionists-neutral" | "shapes";

const BACKGROUNDS = ["ebf2ff", "fef3c7", "ecfdf5", "eeeef4", "eff6ff"].join(",");

/** A stable avatar URL for `seed`. */
export function avatarUrl(seed: string, style: AvatarStyle = "notionists-neutral"): string {
  const params = new URLSearchParams({
    seed,
    backgroundColor: BACKGROUNDS,
    radius: "50",
  });
  return `${BASE}/${style}/svg?${params.toString()}`;
}

/**
 * The two letters shown while the avatar loads, and instead of it if DiceBear
 * is unreachable. A name is split on whitespace so "Kajal Mehta" gives KM
 * rather than KA — a column of first-two-letters is a column of near-duplicates.
 */
export function initialsFor(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "??";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}
