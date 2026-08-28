import { Skeleton } from "@/components/ui/skeleton";

const CARDS = [0, 1, 2, 3, 4, 5];

/**
 * Shown while the most recent run is fetched.
 *
 * The chart block keeps its real height. It is the tallest thing on the page,
 * and a placeholder that did not reserve it would let the metric grid render
 * where the chart is about to land.
 */
export default function BatchLoading() {
  return (
    <>
      <div className="mb-6 space-y-2">
        <Skeleton className="h-8 w-24" />
        <Skeleton className="h-4 w-96" />
      </div>

      <div className="space-y-6">
        <div className="space-y-4 rounded-lg border border-hairline p-5">
          <Skeleton className="h-4 w-72" />
          <Skeleton className="h-3 w-full max-w-xl" />
          <div className="flex gap-3">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-3 w-36" />
          </div>
          <Skeleton className="h-[320px] w-full rounded-md" />
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {CARDS.map((card) => (
            <div key={card} className="space-y-2 rounded-lg border border-hairline p-4">
              <Skeleton className="h-2.5 w-24" />
              <Skeleton className="h-7 w-28" />
              <Skeleton className="h-3 w-full" />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
