import Link from "next/link";
import type { ComponentProps } from "react";

import { Button } from "@/components/ui/button";

type LinkProps = ComponentProps<typeof Link>;
type ButtonProps = ComponentProps<typeof Button>;

interface ButtonLinkProps
  extends Omit<ButtonProps, "render" | "nativeButton" | "href">,
    Pick<LinkProps, "href" | "prefetch" | "replace" | "scroll" | "target" | "rel"> {}

/**
 * A button that navigates.
 *
 * This shadcn style is built on Base UI, not Radix, so there is no `asChild`.
 * Composition happens through `render`, and because the rendered element is an
 * `<a>` rather than a `<button>`, `nativeButton={false}` is required — it tells
 * Base UI to use link keyboard semantics (Enter activates, Space scrolls)
 * instead of button semantics.
 *
 * Wrapping it once keeps every call site from having to remember both halves.
 */
export function ButtonLink({
  href,
  prefetch,
  replace,
  scroll,
  target,
  rel,
  ...props
}: ButtonLinkProps) {
  return (
    <Button
      nativeButton={false}
      render={
        <Link
          href={href}
          prefetch={prefetch}
          replace={replace}
          scroll={scroll}
          target={target}
          rel={rel}
        />
      }
      {...props}
    />
  );
}
