import { Skeleton } from "@/components/ui/skeleton";

const TILES = [0, 1, 2, 3];
const FIELDS = [0, 1, 2, 3];

/**
 * Shown while the ROI figures stream in.
 *
 * The two hero blocks keep their real asymmetry — a 4xl block on the left, a
 * 5xl on the right — so the layout does not jump when the numbers land on a
 * page whose whole point is the size difference between them.
 */
export default function ROILoading() {
  return (
    <>
      <div className="mb-6 space-y-2">
        <Skeleton className="h-8 w-20" />
        <Skeleton className="h-4 w-72" />
      </div>

      <div className="space-y-6">
        <div className="rounded-lg border border-hairline p-5 sm:p-6">
          <div className="grid gap-8 sm:grid-cols-[1fr_auto_1fr] sm:items-start sm:gap-6">
            <div className="space-y-3">
              <Skeleton className="h-2.5 w-28" />
              <Skeleton className="h-10 w-44" />
              <Skeleton className="h-3 w-full max-w-[280px]" />
            </div>
            <Skeleton className="hidden size-5 self-center rounded-none sm:block" />
            <div className="space-y-3">
              <Skeleton className="h-2.5 w-44" />
              <Skeleton className="h-12 w-56" />
              <Skeleton className="h-3 w-full max-w-[280px]" />
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <Skeleton className="h-4 w-44" />
          <div className="grid gap-3 sm:grid-cols-2">
            {TILES.map((tile) => (
              <div key={tile} className="rounded-lg border border-hairline p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1 space-y-2">
                    <Skeleton className="h-4 w-28" />
                    <Skeleton className="h-3 w-full max-w-[240px]" />
                  </div>
                  <Skeleton className="h-5 w-14 shrink-0 rounded-none" />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 border-t border-hairline pt-3 sm:grid-cols-4">
                  {FIELDS.map((field) => (
                    <div key={field} className="space-y-1.5">
                      <Skeleton className="h-2.5 w-12" />
                      <Skeleton className="h-4 w-10" />
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-hairline px-4 py-3">
          <Skeleton className="h-4 w-40" />
        </div>
      </div>
    </>
  );
}
