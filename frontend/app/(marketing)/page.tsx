import { Closing } from "@/components/marketing/Closing";
import { Evidence } from "@/components/marketing/Evidence";
import { Hero } from "@/components/marketing/Hero";
import { LeakIndex } from "@/components/marketing/LeakIndex";
import { Method } from "@/components/marketing/Method";
import { Plate } from "@/components/marketing/Plate";
import { SerifStatement } from "@/components/marketing/SerifStatement";
import { Thesis } from "@/components/marketing/Thesis";
import { PLATES } from "@/lib/assets/images";

/**
 * Type, plate, type, plate — the rhythm the whole page is built on.
 *
 * The plates are not illustrations of the sections around them; they are the
 * pauses that let a 160px headline land. Which is why they carry no copy at all
 * and why they are 85vh: anything shorter reads as a banner between two
 * sections rather than as a held breath.
 *
 * They are deliberately uncaptioned. A caption here would have to name
 * something, and the only honest thing to name is a stock photograph — which is
 * what the footer credit is for. Inventing a project name to sit under it would
 * be borrowing an architecture studio's furniture.
 *
 * Section ids come from `LANDING_SECTIONS`, which the chrome's nav and scroll
 * spy also read — so a section renamed in one place and not the other breaks
 * loudly rather than silently.
 */
export default function LandingPage() {
  return (
    <>
      <Hero />
      <Thesis />
      <Plate image={PLATES.middle} />
      <LeakIndex />
      <SerifStatement />
      <Plate image={PLATES.close} />
      <Method />
      <Evidence />
      <Closing />
    </>
  );
}
