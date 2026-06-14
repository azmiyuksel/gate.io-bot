import { MetricSkeleton, PageSkeleton, TableSkeleton } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <main className="mx-auto max-w-7xl space-y-6 p-6">
      <PageSkeleton />
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricSkeleton />
        <MetricSkeleton />
        <MetricSkeleton />
        <MetricSkeleton />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <TableSkeleton rows={5} cols={7} />
        <div className="rounded-md border bg-white p-5 shadow-sm">
          <div className="h-4 w-32 animate-pulse rounded bg-neutral-200" />
          <div className="mt-4 h-72 animate-pulse rounded bg-neutral-100" />
        </div>
      </div>
      <TableSkeleton rows={5} cols={6} />
      <TableSkeleton rows={5} cols={5} />
    </main>
  );
}
