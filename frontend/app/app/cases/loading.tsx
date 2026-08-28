import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const ROWS = [0, 1, 2, 3, 4, 5, 6, 7];

/**
 * Shown while the cases list streams in.
 *
 * Built from the real `Table` primitives rather than from a stack of plain
 * bars, so the eight columns are laid out by the same code that lays out the
 * loaded table. A hand-approximated grid drifts from the real one the first
 * time a column is added, and the page then visibly re-flows on load — which is
 * the exact jump a skeleton exists to prevent.
 */
export default function CasesLoading() {
  return (
    <>
      <div className="mb-6 space-y-2">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-4 w-40" />
      </div>

      <div className="overflow-x-auto rounded-xl border border-hairline bg-elevated">
        <Table>
          <TableHeader>
            <TableRow className="border-hairline">
              <TableHead className="text-xs font-medium text-ink-faint">Status</TableHead>
              <TableHead className="text-xs font-medium text-ink-faint">Customer</TableHead>
              <TableHead className="text-xs font-medium text-ink-faint">Playbook</TableHead>
              <TableHead className="text-right text-xs font-medium text-ink-faint">
                At Risk
              </TableHead>
              <TableHead className="text-right text-xs font-medium text-ink-faint">
                Recovered
              </TableHead>
              <TableHead className="text-xs font-medium text-ink-faint">Opened</TableHead>
              <TableHead className="text-xs font-medium text-ink-faint">Step</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {ROWS.map((row) => (
              <TableRow key={row} className="border-hairline">
                <TableCell>
                  <Skeleton className="h-5 w-20 rounded-4xl" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-32" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-5 w-24 rounded-4xl" />
                </TableCell>
                <TableCell className="flex justify-end">
                  <Skeleton className="h-4 w-16" />
                </TableCell>
                <TableCell>
                  <Skeleton className="ml-auto h-4 w-16" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-3 w-20" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-5 w-16 rounded" />
                </TableCell>
                <TableCell>
                  <Skeleton className="size-3.5 rounded" />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
}
