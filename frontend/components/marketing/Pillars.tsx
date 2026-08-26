import { CheckCircle, Eye, GitBranch } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface Pillar {
  icon: LucideIcon;
  title: string;
  body: string;
}

const PILLARS: Pillar[] = [
  {
    icon: Eye,
    title: "Detects",
    body: "Watches every Razorpay webhook in real time.",
  },
  {
    icon: GitBranch,
    title: "Decides",
    body: "Contextual bandits learn what works, and what doesn't.",
  },
  {
    icon: CheckCircle,
    title: "Delivers",
    body: "Executes through Razorpay rails, honors every stop.",
  },
];

export function Pillars() {
  return (
    <section id="how-it-works" className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
      <h2 className="font-display text-sm font-semibold tracking-[0.14em] text-ink-faint uppercase">
        How it works
      </h2>

      <div className="mt-10 grid gap-px overflow-hidden rounded-lg border border-hairline bg-hairline sm:grid-cols-3">
        {PILLARS.map(({ icon: Icon, title, body }) => (
          <div key={title} className="bg-elevated p-8">
            <Icon className="size-6 text-brand" strokeWidth={1.5} aria-hidden />
            <h3 className="mt-5 font-display text-xl font-semibold tracking-[-0.02em] text-ink">
              {title}
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">{body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
