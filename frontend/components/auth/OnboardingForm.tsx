"use client";

import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { StaggeredItem } from "@/components/ui/StaggeredItem";
import { ApiError, onboardMerchant } from "@/lib/api/client";
import type { Vertical } from "@/lib/supabase/types";
import { VERTICALS } from "@/lib/verticals";

interface OnboardingFormProps {
  /** From the merchant row, seeded by the signup trigger. */
  initialName: string;
}

export function OnboardingForm({ initialName }: OnboardingFormProps) {
  const router = useRouter();
  const [step, setStep] = useState<1 | 2>(1);
  const [name, setName] = useState(initialName);
  const [vertical, setVertical] = useState<Vertical | null>(null);
  const [pending, setPending] = useState(false);

  function onNameSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    setStep(2);
  }

  async function onFinish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!vertical) return;
    setPending(true);

    try {
      await onboardMerchant({ name: name.trim(), vertical });
      router.replace("/app");
      router.refresh();
    } catch (error) {
      setPending(false);
      if (error instanceof ApiError && error.status === 409) {
        // Already onboarded — a double submit or a stale tab. Nothing is wrong.
        router.replace("/app");
        return;
      }
      toast.error("Could not complete setup", {
        description: error instanceof Error ? error.message : "Please try again.",
      });
    }
  }

  if (step === 1) {
    return (
      <form onSubmit={onNameSubmit} className="grid gap-4">
        <StaggeredItem index={0} className="grid gap-2">
          <Label htmlFor="business-name">Business name</Label>
          <Input
            id="business-name"
            name="name"
            autoComplete="organization"
            required
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <p className="text-xs text-ink-faint">This is the name customers will see in messages.</p>
        </StaggeredItem>

        <StaggeredItem index={1} className="mt-2">
          <Button type="submit" disabled={!name.trim()} className="w-full">
            Continue
          </Button>
        </StaggeredItem>
      </form>
    );
  }

  return (
    <form onSubmit={onFinish} className="grid gap-5">
      <RadioGroup
        value={vertical}
        onValueChange={(value) => setVertical(value as Vertical)}
        aria-label="Vertical"
        className="grid gap-2"
      >
        {/* Wrapping each option rather than the group: the cascade should read
            down the list of choices, which is the order they will be scanned in.
            Base UI's RadioGroup keeps its roving focus through the wrapper — it
            works off context rather than direct children. */}
        {VERTICALS.map((entry, index) => (
          <StaggeredItem key={entry.value} index={index}>
            <Label
              htmlFor={entry.value}
              className="flex cursor-pointer items-start gap-3 rounded-md border border-hairline p-3 transition-colors has-data-checked:border-brand has-data-checked:bg-brand-subtle"
            >
              <RadioGroupItem id={entry.value} value={entry.value} className="mt-0.5" />
              <span className="grid gap-0.5">
                <span className="text-sm font-medium text-ink">{entry.label}</span>
                <span className="text-xs leading-relaxed text-ink-faint">{entry.hint}</span>
              </span>
            </Label>
          </StaggeredItem>
        ))}
      </RadioGroup>

      <div className="flex items-center gap-2">
        <Button type="button" variant="ghost" size="sm" onClick={() => setStep(1)}>
          <ArrowLeft aria-hidden />
          Back
        </Button>
        <Button type="submit" disabled={!vertical || pending} className="flex-1">
          {pending ? "Finishing…" : "Complete setup"}
        </Button>
      </div>
    </form>
  );
}
