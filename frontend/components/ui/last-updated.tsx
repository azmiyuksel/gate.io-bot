import { RefreshCw } from "lucide-react";

export function LastUpdated({ time, onRefresh, loading }: { time: Date | null; onRefresh?: () => void; loading?: boolean }) {
  if (!time) return null;
  return (
    <div className="flex items-center gap-2 text-xs text-muted">
      <span>Son güncelleme: {time.toLocaleTimeString("tr-TR")}</span>
      {onRefresh && (
        <button
          onClick={onRefresh}
          disabled={loading}
          className="text-muted hover:text-foreground disabled:opacity-50"
          aria-label="Yenile"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      )}
    </div>
  );
}
