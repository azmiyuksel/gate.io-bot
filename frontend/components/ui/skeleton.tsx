import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-border", className)} {...props} />;
}

export function CardSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="rounded-md border border-border bg-white p-5 shadow-sm">
      <Skeleton className="mb-4 h-4 w-1/3" />
      <div className="space-y-3">
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-3 w-full" />
        ))}
      </div>
    </div>
  );
}

export function MetricSkeleton() {
  return (
    <div className="rounded-md border border-border bg-white p-5 shadow-sm">
      <Skeleton className="mb-3 h-4 w-1/2" />
      <Skeleton className="h-8 w-2/3" />
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="rounded-md border border-border bg-white p-5 shadow-sm">
      <div className="space-y-3">
        <div className="flex gap-4">
          {Array.from({ length: cols }).map((_, i) => (
            <Skeleton key={i} className="h-4 flex-1" />
          ))}
        </div>
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex gap-4">
            {Array.from({ length: cols }).map((_, c) => (
              <Skeleton key={c} className="h-3 flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChartSkeleton({ height = 288 }: { height?: number }) {
  return (
    <div className="rounded-md border border-border bg-white p-5 shadow-sm">
      <Skeleton className="mb-4 h-4 w-1/4" />
      <Skeleton className="w-full rounded" style={{ height }} />
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="space-y-6 p-6">
      <div className="grid gap-5 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <MetricSkeleton key={i} />
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <ChartSkeleton />
        <ChartSkeleton />
      </div>
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <TableSkeleton rows={4} cols={5} />
        <CardSkeleton rows={4} />
      </div>
    </div>
  );
}
