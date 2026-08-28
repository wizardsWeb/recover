import { Hero } from "@/components/marketing/Hero";
import { HowItWorks } from "@/components/marketing/HowItWorks";
import { MerchantStrip } from "@/components/marketing/MerchantStrip";
import { StatsBar } from "@/components/marketing/StatsBar";

export default function LandingPage() {
  return (
    <>
      <Hero />
      <HowItWorks />
      <StatsBar />
      <MerchantStrip />
    </>
  );
}
