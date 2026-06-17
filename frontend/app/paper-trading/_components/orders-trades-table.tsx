"use client";

import { useEffect, useMemo, useState } from "react";

import { Card } from "@/components/ui/card";
import { fmtPrice, fmtQty, fmtUTC, money } from "@/lib/utils";
import type { PaperTrade } from "@/types/paper";

interface Props {
  trades: PaperTrade[];
}

const PAGE_SIZES = [10, 25, 50, 100];

export default function OrdersTradesTable({ trades }: Props) {
  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<"" | "buy" | "sell">("");
  const [pageSize, setPageSize] = useState(10);
  const [page, setPage] = useState(0);

  // Distinct symbols present in the current trade set, for the filter dropdown.
  const symbols = useMemo(
    () => Array.from(new Set(trades.map((t) => t.symbol))).sort(),
    [trades],
  );

  const filtered = useMemo(
    () =>
      trades.filter(
        (t) => (!symbol || t.symbol === symbol) && (!side || t.side === side),
      ),
    [trades, symbol, side],
  );

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  // Filters/page-size can shrink the result set — keep the page index valid.
  useEffect(() => {
    setPage(0);
  }, [symbol, side, pageSize]);
  useEffect(() => {
    if (page > pageCount - 1) setPage(pageCount - 1);
  }, [page, pageCount]);

  const pageSafe = Math.min(page, pageCount - 1);
  const paged = filtered.slice(pageSafe * pageSize, pageSafe * pageSize + pageSize);

  const selectClass =
    "rounded border border-border bg-white px-2 py-1 text-xs text-foreground";

  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-base font-semibold">Son İşlemler</h2>
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Sembol filtresi"
            className={selectClass}
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
          >
            <option value="">Tüm semboller</option>
            {symbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <select
            aria-label="Yön filtresi"
            className={selectClass}
            value={side}
            onChange={(e) => setSide(e.target.value as "" | "buy" | "sell")}
          >
            <option value="">AL + SAT</option>
            <option value="buy">AL</option>
            <option value="sell">SAT</option>
          </select>
          <select
            aria-label="Sayfa boyutu"
            className={selectClass}
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
          >
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>Son {n}</option>
            ))}
          </select>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border text-muted">
            <tr>
              <th className="py-2" scope="col">Zaman</th>
              <th scope="col">Sembol</th>
              <th scope="col">Yön</th>
              <th scope="col">Fiyat</th>
              <th scope="col">Miktar</th>
              <th scope="col">Ücret</th>
              <th scope="col">PnL</th>
              <th scope="col">Çıkış</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((trade) => {
              const pnl = Number(trade.realized_pnl);
              // A trade with no exit_reason is an OPENING: side=buy opens a LONG,
              // side=sell opens a SHORT (sell-to-open on futures — this is why a
              // "SAT" can appear with no preceding "AL"). Anything with an
              // exit_reason is a CLOSE.
              const isClose = Boolean(trade.exit_reason);
              const isShort = trade.side === "sell";
              const dirLabel = isClose ? "KAPAT" : isShort ? "SHORT" : "LONG";
              const dirClass = isClose
                ? "bg-muted text-foreground"
                : isShort
                  ? "bg-danger text-white"
                  : "bg-primary text-white";
              return (
                <tr key={trade.id} className="border-b border-border">
                  <td className="py-3 text-muted">
                    {fmtUTC(trade.traded_at)}
                  </td>
                  <td className="font-medium">{trade.symbol}</td>
                  <td>
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-semibold uppercase ${dirClass}`}
                      title={`${trade.side === "buy" ? "AL" : "SAT"} · ${isClose ? "kapanış" : "açılış"}`}
                    >
                      {dirLabel}
                    </span>
                  </td>
                  <td>${fmtPrice(trade.price)}</td>
                  <td>{fmtQty(trade.quantity)}</td>
                  <td className="text-muted">${fmtPrice(trade.fee)}</td>
                  <td className={pnl >= 0 ? "font-medium text-primary" : "font-medium text-danger"}>
                    ${money(trade.realized_pnl)}
                  </td>
                  <td className="text-xs text-muted">
                    {trade.exit_reason ? trade.exit_reason.replace(/_/g, " ") : (
                      <span className="rounded bg-blue-100 px-1.5 py-0.5 text-blue-700">AÇILIŞ</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {paged.length === 0 && (
              <tr>
                <td className="py-6 text-muted" colSpan={8}>
                  {trades.length === 0 ? "İşlem geçmişi yok." : "Filtreye uyan işlem yok."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {filtered.length > 0 && (
        <div className="mt-3 flex items-center justify-between text-xs text-muted">
          <span>
            {pageSafe * pageSize + 1}–{Math.min((pageSafe + 1) * pageSize, filtered.length)} /{" "}
            {filtered.length}
            {trades.length >= 100 ? " (son 100 işlem)" : ""}
          </span>
          {pageCount > 1 && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={pageSafe === 0}
                className="rounded border border-border px-2 py-1 disabled:opacity-40"
              >
                Önceki
              </button>
              <span className="px-1 py-1">{pageSafe + 1}/{pageCount}</span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                disabled={pageSafe >= pageCount - 1}
                className="rounded border border-border px-2 py-1 disabled:opacity-40"
              >
                Sonraki
              </button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
