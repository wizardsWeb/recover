"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { updateMerchant } from "@/lib/api/client";
import type { Vertical } from "@/lib/supabase/types";
import { TIMEZONES, VERTICALS } from "@/lib/verticals";

interface ProfileFormProps {
  initialName: string;
  initialVertical: Vertical | null;
  initialTimezone: string;
}

export function ProfileForm({ initialName, initialVertical, initialTimezone }: ProfileFormProps) {
  const router = useRouter();
  const [name, setName] = useState(initialName);
  const [vertical, setVertical] = useState<Vertical | "">(initialVertical ?? "");
  const [timezone, setTimezone] = useState(initialTimezone);
  const [pending, setPending] = useState(false);

  const dirty =
    name !== initialName || vertical !== (initialVertical ?? "") || timezone !== initialTimezone;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);

    try {
      await updateMerchant({
        name: name.trim(),
        ...(vertical ? { vertical } : {}),
        timezone,
      });
      // The layout header and this form both render from the merchant row, so
      // the server components have to re-run for the new name to show up there.
      router.refresh();
      toast.success("Profile saved");
    } catch (error) {
      toast.error("Could not save profile", {
        description: error instanceof Error ? error.message : "Please try again.",
      });
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="grid max-w-lg gap-5">
      <div className="grid gap-2">
        <Label htmlFor="name">Business name</Label>
        <Input
          id="name"
          name="name"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <p className="text-xs text-ink-faint">The name customers see in recovery messages.</p>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="vertical">Vertical</Label>
        <NativeSelect
          id="vertical"
          name="vertical"
          className="w-full"
          value={vertical}
          onChange={(event) => setVertical(event.target.value as Vertical)}
        >
          <NativeSelectOption value="" disabled>
            Select a vertical
          </NativeSelectOption>
          {VERTICALS.map((entry) => (
            <NativeSelectOption key={entry.value} value={entry.value}>
              {entry.label}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <p className="text-xs text-ink-faint">Sets which playbooks the agent reaches for first.</p>
      </div>

      <div className="grid gap-2">
        <Label htmlFor="timezone">Timezone</Label>
        <NativeSelect
          id="timezone"
          name="timezone"
          className="w-full"
          value={timezone}
          onChange={(event) => setTimezone(event.target.value)}
        >
          {TIMEZONES.map((zone) => (
            <NativeSelectOption key={zone} value={zone}>
              {zone}
            </NativeSelectOption>
          ))}
        </NativeSelect>
        <p className="text-xs text-ink-faint">
          Quiet hours and send windows are evaluated in this zone.
        </p>
      </div>

      <div>
        <Button type="submit" disabled={pending || !dirty || !name.trim()}>
          {pending ? "Saving…" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}
