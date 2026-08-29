import Image from "next/image";

import type { StockImage } from "@/lib/assets/images";
import { cn } from "@/lib/utils/cn";

/**
 * A full-bleed photograph, optionally with a caption hung off one corner.
 *
 * Edge to edge with no gutter and no radius. The reference alternates type and
 * plate down the whole page, and the plates are what give the type its silence
 * — so they are tall (85vh) and carry nothing but the image and, sometimes, a
 * 13px line naming what it is.
 *
 * `sizes="100vw"` because that is literally true, and getting it wrong is how a
 * full-bleed image ends up downloading a 640px rendition and looking soft.
 */
export function Plate({
  image,
  caption,
  priority = false,
  className,
}: {
  image: StockImage;
  caption?: string;
  priority?: boolean;
  className?: string;
}) {
  return (
    <figure className={cn("relative h-[70vh] w-full overflow-hidden sm:h-[85vh]", className)}>
      <Image
        src={image.src}
        alt={image.alt}
        fill
        sizes="100vw"
        priority={priority}
        className="object-cover"
      />
      {caption ? (
        <figcaption className="absolute bottom-4 left-5 text-[13px] text-white/70 sm:left-7">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}
