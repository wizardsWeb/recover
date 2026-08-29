/**
 * The landing page's sections, in the order they appear.
 *
 * One list, read by three things: the nav renders it, the scroll spy observes
 * these ids, and each section takes its own id from the same strings.
 *
 * The labels are one word each and lowercase-cased as nouns, joined by commas
 * in the nav the way an index is. "Leaks" rather than "Product", "Method"
 * rather than "How it works": this is a page about a subject, and the nav is a
 * table of contents for it, not a menu of marketing pages.
 */
export interface LandingSection {
  id: string;
  label: string;
}

export const LANDING_SECTIONS: readonly LandingSection[] = [
  { id: "index", label: "Index" },
  { id: "leaks", label: "Leaks" },
  { id: "method", label: "Method" },
  { id: "evidence", label: "Evidence" },
  { id: "start", label: "Start" },
];
