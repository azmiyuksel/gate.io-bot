import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function Metric({
  label,
  value,
  icon,
  className,
  color,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
  className?: string;
  color?: string;
}) {
  return (
    <Card className={className}>
      <div className="mb-3 flex items-center justify-between text-muted">
        <span className="text-sm">{label}</span>
        {icon}
      </div>
      <div className="text-2xl font-semibold" style={color ? { color } : undefined}>
        {value}
      </div>
    </Card>
  );
}

export function MetricCompact({
  label,
  value,
  icon,
  trend,
}: {
  label: string;
  value: string;
  icon?: React.ReactNode;
  trend?: "positive" | "negative" | "neutral";
}) {
  return (
    <div className="flex items-center gap-3">
      {icon && <div className="text-muted">{icon}</div>}
      <div>
        <p className="text-xs text-muted">{label}</p>
        <p
          className={cn(
            "text-sm font-semibold",
            trend === "positive" && "text-green-600",
            trend === "negative" && "text-danger",
          )}
        >
          {value}
        </p>
      </div>
    </div>
  );
}
