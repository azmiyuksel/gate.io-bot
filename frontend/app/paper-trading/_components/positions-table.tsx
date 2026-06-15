"use client";

import { X } from "lucide-react";

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
              <th scope="col">Miktar</th>
              <th scope="col">Giriş</th>
              <th scope="col">Güncel</th>
              <th scope="col">PnL</th>
              <th scope="col">PnL%</th>
              <th scope="col">Stop</th>
              <th scope="col">Hedef</th>
              <th scope="col"></th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => {
              const pnl = Number(pos.unrealized_pnl);
              const cost = Number(pos.quantity) * Number(pos.average_entry_price);
              const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;
              return (
                <tr key={pos.id} className="border-b border-border">
                  <td className="py-3 font-medium">{pos.symbol}</td>
                  <td>
                    <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold uppercase text-white ${pos.side === "sell" ? "bg-danger" : "bg-primary"}`}>
                      {pos.side === "sell" ? "SHORT" : "LONG"}
                    </span>
                  </td>
                  <td>{fmtQty(pos.quantity)}</td>
                  <td>${fmtPrice(pos.average_entry_price)}</td>
                  <td>${fmtPrice(pos.last_price)}</td>
                  <td className={pnl >= 0 ? "text-primary font-medium" : "text-danger font-medium"}>
                    ${money(pos.unrealized_pnl)}
                  </td>
                  <td className={pnlPct >= 0 ? "text-primary" : "text-danger"}>
                    {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
                  </td>
                  <td className={pos.stop_loss ? "text-danger" : "text-muted"}>
                    {pos.stop_loss ? `$${fmtPrice(pos.stop_loss)}` : "-"}
                  </td>
                  <td className={pos.take_profit ? "text-primary" : "text-muted"}>
                    {pos.take_profit ? `$${fmtPrice(pos.take_profit)}` : "-"}
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
                <td className="py-6 text-muted" colSpan={10}>Açık pozisyon yok.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
