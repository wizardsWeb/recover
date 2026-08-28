import { Skeleton } from "@/components/ui/skeleton";

const BANKS = [0, 1, 2, 3, 4];
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);
const FIGURES = [0, 1, 2];

/**
 * Shown while the network reads stream in.
 *
 * The grid is drawn at full size rather than as one block. It is the tallest
 * thing on the page, and a placeholder that does not reserve its height lets
 * the benchmark panel render where the heatmap is about to land.
 */
export default function NetworkLoading() {
  return (
    <>
      <div className="mb-6 space-y-2">
        <Skeleton className="h-8 w-28" />
        <Skeleton className="h-4 w-80" />
      </div>

      <div className="space-y-6">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-16" />
          </div>
          <Skeleton className="h-[76px] w-full rounded-lg" />
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-6 w-40 rounded-md" />
          </div>
          <div className="overflow-x-auto rounded-lg border border-hairline bg-elevated p-3">
            <div className="min-w-[720px] space-y-px">
              {BANKS.map((bank) => (
                <div key={bank} className="flex items-center gap-2">
                  <Skeleton className="h-3 w-14 shrink-0" />
                  <div className="flex flex-1 gap-px">
                    {HOURS.map((hour) => (
                      <Skeleton key={hour} className="h-6 flex-1 rounded-[3px]" />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-hairline p-5">
          <Skeleton className="h-4 w-64" />
          <div className="mt-4 grid grid-cols-3 gap-4">
            {FIGURES.map((figure) => (
              <div key={figure} className="space-y-1.5">
                <Skeleton className="h-2.5 w-20" />
                <Skeleton className="h-7 w-16" />
              </div>
            ))}
          </div>
          <Skeleton className="mt-5 h-2 w-full rounded-full" />
        </div>
      </div>
    </>
  );
}
