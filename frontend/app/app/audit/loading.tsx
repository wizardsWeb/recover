import { Skeleton } from "@/components/ui/skeleton";

const ROWS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];

/**
 * Shown while the audit trail streams in.
 *
 * Each row carries the loaded entry's four fixed slots — chevron, timestamp,
 * actor badge, event label — at the same widths, so the columns do not shift
 * under the reader when the real rows arrive.
 */
export default function AuditLoading() {
  return (
    <>
      <div className="mb-6 space-y-2">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-4 w-80" />
      </div>

      <div className="mt-6 overflow-hidden rounded-none border border-hairline bg-elevated">
        <div className="divide-y divide-hairline">
          {ROWS.map((row) => (
            <div key={row} className="flex items-center gap-3 px-4 py-3">
              <Skeleton className="size-3 shrink-0 rounded" />
              <Skeleton className="h-3 w-24 shrink-0" />
              <Skeleton className="h-5 w-16 shrink-0 rounded-none" />
              <Skeleton className="h-4 w-full max-w-[280px]" />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
