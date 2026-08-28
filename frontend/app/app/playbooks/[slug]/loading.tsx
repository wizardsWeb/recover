import { Skeleton } from "@/components/ui/skeleton";

const STATS = [0, 1, 2, 3];
const ARMS = [0, 1, 2, 3, 4, 5];
const ROWS = [0, 1, 2, 3, 4];

/**
 * Shown while a playbook's detail streams in.
 *
 * Mirrors the loaded page in order: the four-up stats strip, the arms list, and
 * the recent-cases table. The arm bars are skeletons at full width rather than
 * at a guessed length — a skeleton that implies a value the data has not
 * returned yet is a chart of nothing.
 */
export default function PlaybookDetailLoading() {
  return (
    <>
      <div className="mb-6 space-y-2">
        <Skeleton className="h-8 w-52" />
        <Skeleton className="h-4 w-72" />
      </div>

      <section className="grid grid-cols-2 gap-6 rounded-lg border border-hairline p-4 sm:grid-cols-4">
        {STATS.map((stat) => (
          <div key={stat} className="space-y-2">
            <Skeleton className="h-2.5 w-16" />
            <Skeleton className="h-6 w-20" />
          </div>
        ))}
      </section>

      <section className="mt-6 space-y-3">
        <Skeleton className="h-4 w-16" />
        <div className="space-y-2">
          {ARMS.map((arm) => (
            <div key={arm} className="flex items-center gap-2">
              <Skeleton className="h-3 w-[180px] shrink-0" />
              <Skeleton className="h-2 flex-1 rounded-4xl" />
              <Skeleton className="h-3 w-10 shrink-0" />
            </div>
          ))}
        </div>
      </section>

      <section className="mt-6 space-y-3">
        <Skeleton className="h-4 w-28" />
        <div className="space-y-2 rounded-lg border border-hairline p-4">
          {ROWS.map((row) => (
            <div key={row} className="flex items-center gap-4">
              <Skeleton className="h-5 w-20 rounded-4xl" />
              <Skeleton className="h-4 flex-1 max-w-[200px]" />
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-3 w-20" />
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
