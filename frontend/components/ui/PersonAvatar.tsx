import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { avatarUrl, initialsFor, type AvatarStyle } from "@/lib/assets/avatar";
import { cn } from "@/lib/utils/cn";

interface PersonAvatarProps {
  /** Stable identity — an id, not a display name. See `avatarUrl`. */
  seed: string;
  /** Used for the initials fallback and the accessible name. */
  name: string;
  className?: string;
  style?: AvatarStyle;
}

/**
 * A customer's face, wherever one is shown.
 *
 * A server component: the URL is a pure function of the seed, so there is
 * nothing here that needs to run in the browser. Sizing is left to the caller's
 * `className` because the three sizes in the product — 28px in a table row,
 * 32px in the rail, 56px on the case detail — are not a scale worth naming.
 */
export function PersonAvatar({ seed, name, className, style }: PersonAvatarProps) {
  return (
    <Avatar className={cn("size-7", className)}>
      <AvatarImage src={avatarUrl(seed, style)} alt="" />
      <AvatarFallback className="bg-brand-subtle text-[10px] font-medium text-brand">
        {initialsFor(name)}
      </AvatarFallback>
    </Avatar>
  );
}
