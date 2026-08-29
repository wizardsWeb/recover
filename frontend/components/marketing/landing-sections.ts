/**
 * The landing page's nav destinations, in the order they appear on the page.
 *
 * One list, read by three things: the floating nav renders it, the scroll spy
 * observes these ids, and each section takes its own id from the same strings.
 * A second hand-written copy inside the nav is the version that silently points
 * at a section somebody renamed.
 *
 * The brief's fifth link was "Pricing". There is no pricing page and no pricing
 * — a nav item that promises one and scrolls to a call-to-action is a small lie
 * told in the most prominent element on the page — so that slot is "Results",
 * which is a section that exists.
 */
export interface LandingSection {
  id: string;
  label: string;
}

export const LANDING_SECTIONS: readonly LandingSection[] = [
  { id: "top", label: "Home" },
  { id: "leaks", label: "Product" },
  { id: "how-it-works", label: "Case studies" },
  { id: "results", label: "Results" },
  { id: "start", label: "Contact" },
];
