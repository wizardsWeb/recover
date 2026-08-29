"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { PersonAvatar } from "@/components/ui/PersonAvatar";
import { createClient } from "@/lib/supabase/client";

interface UserMenuProps {
  email: string;
  businessName: string;
}

export function UserMenu({ email, businessName }: UserMenuProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);

  async function signOut() {
    setPending(true);
    const supabase = createClient();
    const { error } = await supabase.auth.signOut();

    if (error) {
      setPending(false);
      toast.error("Could not sign out", { description: error.message });
      return;
    }

    router.replace("/");
    router.refresh();
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="icon" aria-label="Account menu">
            {/* Seeded on the email so the header and the rail show the same
                face — the rail seeds on the same value for that reason. */}
            <PersonAvatar seed={email || businessName} name={businessName} />
          </Button>
        }
      />
      {/* w-56 overrides the popup's default w-(--anchor-width), which would
          otherwise size the menu to the icon button that opened it. */}
      <DropdownMenuContent align="end" className="w-56">
        <div className="px-2 py-1.5">
          <p className="truncate text-sm font-medium text-ink">{businessName}</p>
          <p className="truncate font-mono text-xs text-ink-faint">{email}</p>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={signOut} disabled={pending}>
          <LogOut aria-hidden />
          {pending ? "Signing out…" : "Sign out"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
