import { Skeleton } from "@/components/ui/skeleton";

const CARDS = [0, 1, 2, 3];
const STATS = [0, 1, 2, 3];

/**
 * Shown while the playbooks list streams in.
 *
 * Four cards on the same `sm:grid-cols-2` the loaded page uses, each carrying
 * the four-stat strip that sits under its title.
 */
export default function PlaybooksLoading() {
  return (
    <>
      <div className="mb-6 space-y-2">
        <Skeleton className="h-8 w-36" />
        <Skeleton className="h-4 w-56" />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {CARDS.map((card) => (
          <div key={card} className="rounded-lg border border-hairline p-4">
            <div className="flex items-start gap-3">
              <Skeleton className="mt-0.5 size-7 shrink-0 rounded-full" />
              <div className="min-w-0 flex-1 space-y-2">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-3 w-full max-w-[280px]" />
              </div>
              <Skeleton className="h-5 w-9 shrink-0 rounded-4xl" />
            </div>

            <div className="mt-4 grid grid-cols-4 gap-3 border-t border-hairline pt-3">
              {STATS.map((stat) => (
                <div key={stat} className="space-y-1.5">
                  <Skeleton className="h-2.5 w-12" />
                  <Skeleton className="h-4 w-10" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
