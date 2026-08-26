import type { LucideIcon } from "lucide-react";

interface ComingSoonProps {
  icon: LucideIcon;
  /** Which phase delivers this section, e.g. "Phase 3". */
  phase: string;
  description: string;
}

/** The shared placeholder for sections that ship in a later phase. */
export function ComingSoon({ icon: Icon, phase, description }: ComingSoonProps) {
  return (
    <div className="rounded-lg border border-hairline bg-elevated p-2">
      <div className="flex flex-col items-center rounded-md bg-subtle px-8 py-16 text-center">
        <Icon className="size-12 text-ink-faint" strokeWidth={1} aria-hidden />
        <p className="mt-6 font-display text-sm font-semibold tracking-[0.1em] text-brand uppercase">
          Coming in {phase}
        </p>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-ink-muted">{description}</p>
      </div>
    </div>
  );
}
