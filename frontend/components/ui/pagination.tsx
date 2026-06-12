import { useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

export function usePagination<T>(items: T[], pageSize: number) {
  const [page, setPage] = useState(1);
  const totalPages = Math.ceil(items.length / pageSize);
  const paginatedItems = items.slice((page - 1) * pageSize, page * pageSize);

  return { page, setPage, totalPages, paginatedItems };
}

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null;

  const pages: (number | "...")[] = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (page > 3) pages.push("...");
    for (let i = Math.max(2, page - 1); i <= Math.min(totalPages - 1, page + 1); i++) {
      pages.push(i);
    }
    if (page < totalPages - 2) pages.push("...");
    pages.push(totalPages);
  }

  return (
    <nav aria-label="Sayfalama" className="flex items-center gap-1">
      <Button
        className="h-8 w-8 p-0"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        aria-label="Önceki sayfa"
      >
        <ChevronLeft size={14} />
      </Button>
      {pages.map((p, i) =>
        p === "..." ? (
          <span key={`dots-${i}`} className="px-1 text-muted">
            ...
          </span>
        ) : (
          <Button
            key={p}
            className={`h-8 w-8 p-0 ${p === page ? "bg-primary text-white" : "bg-transparent text-foreground hover:bg-border/60"}`}
            onClick={() => onPageChange(p)}
            aria-label={`Sayfa ${p}`}
            aria-current={p === page ? "page" : undefined}
          >
            {p}
          </Button>
        ),
      )}
      <Button
        className="h-8 w-8 p-0"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        aria-label="Sonraki sayfa"
      >
        <ChevronRight size={14} />
      </Button>
    </nav>
  );
}
