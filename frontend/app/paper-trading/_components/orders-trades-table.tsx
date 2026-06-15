"use client";

import { Card } from "@/components/ui/card";
import { fmtPrice, fmtQty, fmtUTC, money } from "@/lib/utils";
import type { PaperTrade } from "@/types/paper";

interface Props {
  trades: PaperTrade[];
}

export default function OrdersTradesTable({ trades }: Props) {
  return (
    <Card>
      <h2 className="mb-4 text-base font-semibold">Son İşlemler</h2>
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
            {trades.map((trade) => {
              const pnl = Number(trade.realized_pnl);
              return (
                <tr key={trade.id} className="border-b border-border">
                  <td className="py-3 text-muted">
                    {fmtUTC(trade.traded_at)}
                  </td>
                  <td className="font-medium">{trade.symbol}</td>
                  <td>
                    <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold uppercase text-white ${trade.side === "buy" ? "bg-primary" : "bg-danger"}`}>
                      {trade.side === "buy" ? "AL" : "SAT"}
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
            {trades.length === 0 && (
              <tr>
                <td className="py-6 text-muted" colSpan={8}>İşlem geçmişi yok.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
