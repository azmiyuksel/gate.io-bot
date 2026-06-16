"use client";

import { Activity } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Card } from "@/components/ui/card";
import { fmtUTC } from "@/lib/utils";
import type { PaperSignalDiagnostics } from "@/types/paper";

interface Props {
  diagnostics: PaperSignalDiagnostics | null;
  maxReasonCount: number;
}

// Cap how much each panel can render so the page never grows unbounded as more
// reasons/symbols accumulate. Reasons scroll inside a fixed height; the symbol
// table is paginated.
const REASONS_VISIBLE = 8;
const SYMBOLS_PER_PAGE = 10;

export default function SignalDiagnostics({ diagnostics, maxReasonCount }: Props) {
  const [showAllReasons, setShowAllReasons] = useState(false);
  const [page, setPage] = useState(0);

  const reasonEntries = useMemo(
    () => Object.entries(diagnostics?.reason_counts ?? {}),
    [diagnostics],
  );
  // Newest-first so the most relevant symbols lead the (paginated) table.
  const symbolEntries = useMemo(
    () =>
      Object.entries(diagnostics?.latest_by_symbol ?? {}).sort(
        ([, a], [, b]) => (b.at ?? "").localeCompare(a.at ?? ""),
      ),
    [diagnostics],
  );

  const pageCount = Math.max(1, Math.ceil(symbolEntries.length / SYMBOLS_PER_PAGE));
  // Keep the current page valid when the underlying data shrinks.
  useEffect(() => {
    if (page > pageCount - 1) setPage(pageCount - 1);
  }, [page, pageCount]);

  const pageSafe = Math.min(page, pageCount - 1);
  const pagedSymbols = symbolEntries.slice(
    pageSafe * SYMBOLS_PER_PAGE,
    pageSafe * SYMBOLS_PER_PAGE + SYMBOLS_PER_PAGE,
  );
  const visibleReasons = showAllReasons ? reasonEntries : reasonEntries.slice(0, REASONS_VISIBLE);

  return (
    <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[1fr_1fr]">
      <Card>
        <div className="mb-1 flex items-center gap-2">
          <Activity size={17} />
          <h2 className="text-base font-semibold">Sinyal Tanılama</h2>
        </div>
        <p className="mb-2 text-sm text-muted">
          Son {diagnostics?.window_hours ?? 24} saatte girişlerin neden atlandığı
          {diagnostics ? ` (${diagnostics.evaluations} değerlendirme)` : ""}.
        </p>
        {diagnostics && diagnostics.evaluations === 0 && (
          <div className="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            Hiç değerlendirme kaydı yok. <strong>paper-worker</strong> servisi
            çalışmıyor olabilir veya worker dış ağa (Gate.io) erişemiyor olabilir.
            <code className="ml-1">docker compose logs -f paper-worker</code> ile kontrol edin.
          </div>
        )}
        {diagnostics?.last_evaluation_at && (
          <p className="mb-4 text-xs text-muted">
            Son değerlendirme: {fmtUTC(diagnostics.last_evaluation_at, true)}
          </p>
        )}
        {reasonEntries.length > 0 ? (
          <>
            <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
              {visibleReasons.map(([reason, count]) => {
                const pct = (count / maxReasonCount) * 100;
                const approved =
                  reason.startsWith("approved") ||
                  reason.startsWith("long_entry") ||
                  reason.startsWith("short_entry");
                return (
                  <div key={reason}>
                    <div className="flex items-center justify-between text-sm">
                      <span className={approved ? "font-medium text-primary" : ""}>{reason}</span>
                      <span className="text-muted">{count}</span>
                    </div>
                    <div className="mt-1 h-1.5 w-full rounded bg-border">
                      <div
                        className={`h-1.5 rounded ${approved ? "bg-primary" : "bg-amber-600"}`}
                        style={{ width: `${Math.round(pct)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            {reasonEntries.length > REASONS_VISIBLE && (
              <button
                type="button"
                onClick={() => setShowAllReasons((v) => !v)}
                className="mt-3 text-xs font-medium text-primary hover:underline"
              >
                {showAllReasons
                  ? "Daha az göster"
                  : `Tümünü göster (${reasonEntries.length})`}
              </button>
            )}
          </>
        ) : (
          <p className="text-sm text-muted">Henüz değerlendirme kaydı yok.</p>
        )}
      </Card>

      <Card>
        <div className="mb-4 flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold">Sembol Bazında Son Durum</h2>
          {symbolEntries.length > 0 && (
            <span className="text-xs text-muted">{symbolEntries.length} sembol</span>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border text-muted">
              <tr>
                <th className="py-2" scope="col">Sembol</th>
                <th scope="col">Son Neden</th>
                <th scope="col">Zaman</th>
              </tr>
            </thead>
            <tbody>
              {pagedSymbols.length > 0 ? (
                pagedSymbols.map(([symbol, info]) => (
                  <tr key={symbol} className="border-b border-border">
                    <td className="py-3 font-medium">{symbol}</td>
                    <td
                      className={
                        info.reason.includes("entry") || info.reason === "approved"
                          ? "text-primary font-medium"
                          : "text-muted"
                      }
                    >
                      {info.reason}
                    </td>
                    <td className="text-xs text-muted">{info.at ? fmtUTC(info.at, true) : "-"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="py-6 text-muted" colSpan={3}>Kayıt yok.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {pageCount > 1 && (
          <div className="mt-3 flex items-center justify-between text-xs text-muted">
            <span>
              {pageSafe * SYMBOLS_PER_PAGE + 1}–
              {Math.min((pageSafe + 1) * SYMBOLS_PER_PAGE, symbolEntries.length)} /{" "}
              {symbolEntries.length}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={pageSafe === 0}
                className="rounded border border-border px-2 py-1 disabled:opacity-40"
              >
                Önceki
              </button>
              <span className="px-1 py-1">
                {pageSafe + 1}/{pageCount}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                disabled={pageSafe >= pageCount - 1}
                className="rounded border border-border px-2 py-1 disabled:opacity-40"
              >
                Sonraki
              </button>
            </div>
          </div>
        )}
      </Card>
    </section>
  );
}
