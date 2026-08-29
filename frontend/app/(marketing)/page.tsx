import { AgentSection } from "@/components/marketing/AgentSection";
import { CtaSection } from "@/components/marketing/CtaSection";
import { Hero } from "@/components/marketing/Hero";
import { HowItWorks } from "@/components/marketing/HowItWorks";
import { LeakSection } from "@/components/marketing/LeakSection";
import { MetricsSection } from "@/components/marketing/MetricsSection";

/**
 * Six sections, alternating dark and light so the page has a rhythm rather than
 * a scroll length. The ids each section carries are the ones `LANDING_SECTIONS`
 * names — the floating nav and the scroll spy both read that list, so a section
 * renamed here without renaming it there breaks loudly rather than silently.
 */
export default function LandingPage() {
  return (
    <>
      <Hero />
      <LeakSection />
      <HowItWorks />
      <AgentSection />
      <MetricsSection />
      <CtaSection />
    </>
  );
}
