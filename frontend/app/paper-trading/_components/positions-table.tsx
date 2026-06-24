"use client";

import { CheckCircle2, X } from "lucide-react";

import { Card } from "@/components/ui/card";
import { closePaperPosition } from "@/lib/paper-api";
import { fmtPrice, fmtQty, money } from "@/lib/utils";
import type { PaperPosition } from "@/types/paper";

type ActionFn = (fn: () => Promise<boolean>, successMsg: string, btnId?: string) => Promise<void>;

interface Props {
  positions: PaperPosition[];
  actionLoadingBtn: string;
  onAction: ActionFn;
}

function fmtDuration(openedAt: string | null): string {
  if (!openedAt) return "-";
  const ms = Date.now() - new Date(openedAt).getTime();
  if (ms < 0) return "0m";
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  if (h > 48) return `${Math.floor(h / 24)}g ${h % 24}s`;
  if (h > 0) return `${h}s ${m}d`;
  return `${m}d`;
}

export default function PositionsTable({ positions, actionLoadingBtn, onAction }: Props) {
  return (
    <Card>
      <h2 className="mb-4 text-base font-semibold">Açık Pozisyonlar</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border text-muted">
            <tr>
              <th className="py-2" scope="col">Sembol</th>
              <th scope="col">Yön</th>
              <th scope="col">Süre</th>
              <th scope="col">Miktar</th>
              <th scope="col">Giriş</th>
              <th scope="col">Güncel</th>
              <th scope="col">PnL</th>
              <th scope="col">PnL%</th>
              <th scope="col">R</th>
              <th scope="col">Stop</th>
              <th scope="col"></th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => {
              const pnl = Number(pos.unrealized_pnl);
              const cost = Number(pos.quantity) * Number(pos.average_entry_price);
              const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;
              const entry = Number(pos.average_entry_price);
              const sl = Number(pos.initial_stop_loss || pos.stop_loss || 0);
              const r = sl > 0 ? Math.abs(entry - sl) : 0;
              const rMultiple = r > 0 ? pnl / (cost / entry * r) : 0;
              const trailing = Number(pos.trailing_stop || 0);
              return (
                <tr key={pos.id} className="border-b border-border">
                  <td className="py-3 font-medium">
                    <div className="flex items-center gap-1.5">
                      {pos.symbol}
                      {pos.scaled_out && (
                        <span className="inline-flex items-center gap-0.5 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary" title="Kâr aldı">
                          <CheckCircle2 size={10} /> KÂR
                        </span>
                      )}
                      {pos.breakeven_triggered && !pos.scaled_out && (
                        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700" title="Başabaşa çekildi">
                          BE
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold uppercase text-white ${pos.side === "short" ? "bg-danger" : "bg-primary"}`}>
                      {pos.side === "short" ? "SHORT" : "LONG"}
                    </span>
                  </td>
                  <td className="text-muted text-xs">{fmtDuration(pos.opened_at)}</td>
                  <td>{fmtQty(pos.quantity)}</td>
                  <td>${fmtPrice(pos.average_entry_price)}</td>
                  <td>${fmtPrice(pos.last_price)}</td>
                  <td className={pnl >= 0 ? "text-primary font-medium" : "text-danger font-medium"}>
                    ${money(pos.unrealized_pnl)}
                  </td>
                  <td className={pnlPct >= 0 ? "text-primary" : "text-danger"}>
                    {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
                  </td>
                  <td className={rMultiple >= 0 ? "text-primary" : "text-danger"}>
                    {rMultiple >= 0 ? "+" : ""}{rMultiple.toFixed(1)}R
                  </td>
                  <td className="text-muted text-xs" title={trailing > 0 ? `Trailing: $${fmtPrice(trailing)}` : pos.initial_stop_loss ? "Initial SL" : ""}>
                    {sl > 0 ? (
                      <span className={trailing > 0 ? "text-amber-600" : ""}>
                        ${fmtPrice(sl)}
                      </span>
                    ) : "-"}
                  </td>
                  <td>
                    <button
                      onClick={() => onAction(() => closePaperPosition(pos.id), `${pos.symbol} kapatıldı`, `close-${pos.id}`)}
                      disabled={!!actionLoadingBtn}
                      className="rounded bg-danger/10 px-2 py-1 text-xs font-medium text-danger hover:bg-danger/20"
                    >
                      <X size={12} className="inline" /> Kapat
                    </button>
                  </td>
                </tr>
              );
            })}
            {positions.length === 0 && (
              <tr>
                <td className="py-6 text-muted" colSpan={11}>Açık pozisyon yok.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
