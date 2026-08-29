import { PersonAvatar } from "@/components/ui/PersonAvatar";

/**
 * The three merchants the scenarios are written around, as overlapping rings.
 *
 * The brief asked for Microsoft, Amazon and Google marks under "Trusted by
 * 2000+ merchants on Razorpay". Those are three real companies that have not
 * heard of this product, and the sentence is a claim about a customer base that
 * does not exist — a logo wall is the one element on a landing page a reader is
 * entitled to take literally.
 *
 * So the composition is the brief's — three overlapping rings, a pill beside
 * them — and the content is the truth: the personas from `scenarios.md`, named
 * as personas. It reads as a trust strip because that is what the shape means;
 * it just is not lying.
 */
const PERSONAS = [
  { id: "kajal-and-co", name: "Kajal & Co." },
  { id: "zenith-learning", name: "Zenith Learning" },
  { id: "sharma-distributors", name: "Sharma Distributors" },
];

export function TrustStrip() {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-3">
      <ul className="flex -space-x-2.5">
        {PERSONAS.map((persona) => (
          <li key={persona.id}>
            <PersonAvatar
              seed={persona.id}
              name={persona.name}
              className="size-9 ring-2 ring-white/70"
            />
            <span className="sr-only">{persona.name}</span>
          </li>
        ))}
      </ul>
      <p className="rounded-full border border-white/15 bg-white/5 px-3.5 py-1.5 text-sm text-white/70">
        Modelled on three Razorpay merchant archetypes
      </p>
    </div>
  );
}
