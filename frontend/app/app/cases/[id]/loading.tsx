import { Skeleton } from "@/components/ui/skeleton";

/**
 * Shown while the case detail streams in.
 *
 * The shape mirrors the real page — timeline on the left, cards on the right —
 * so the layout does not jump when the data lands.
 */
export default function CaseDetailLoading() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-48" />
      <div className="mt-6 grid grid-cols-[1fr_320px] gap-6">
        <div className="space-y-3">
          {[0, 1, 2, 3, 4].map((row) => (
            <Skeleton key={row} className="h-14 w-full rounded-lg" />
          ))}
        </div>
        <div className="space-y-3">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-28 w-full rounded-xl" />
        </div>
      </div>
    </div>
  );
}
