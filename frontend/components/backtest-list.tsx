"use client";

import Link from "next/link";
import { Activity, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { money } from "@/lib/utils";
import { authFetch, getAccessToken } from "@/lib/auth-api";
import type { BacktestListItem } from "@/types/backtest";

export function BacktestList() {
  const [token, setToken] = useState("");
  const [runs, setRuns] = useState<BacktestListItem[]>([]);

  async function refresh() {
    if (!token) return;
    const response = await authFetch(`/backtests`);
    if (response.ok) setRuns(await response.json());
  }

  async function remove(id: number) {
    await authFetch(`/backtests/${id}`, { method: "DELETE" });
    await refresh();
  }

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  useEffect(() => {
    refresh();
  }, [token]);

  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold">Backtests</h1>
            <p className="text-sm text-muted">Strateji performansını geçmiş veri üzerinde karşılaştır</p>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={refresh}><Activity size={16} /> Yenile</Button>
            <Link href="/backtests/create">
              <Button><Plus size={16} /> Yeni</Button>
            </Link>
          </div>
        </div>
      </header>

      <section className="mx-auto px-6 py-6 max-w-7xl">
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2">Tarih</th>
                  <th>Strateji</th>
                  <th>Sembol</th>
                  <th>Net Kar</th>
                  <th>Sharpe</th>
                  <th>Max DD</th>
                  <th>Durum</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className="border-b border-border">
                    <td className="py-3">{new Date(run.created_at).toLocaleString()}</td>
                    <td>{run.strategy_name}</td>
                    <td>{run.symbol} · {run.timeframe}</td>
                    <td>${money(run.net_profit)}</td>
                    <td>{run.sharpe_ratio.toFixed(2)}</td>
                    <td>{(run.max_drawdown * 100).toFixed(2)}%</td>
                    <td>{run.status}</td>
                    <td className="flex justify-end gap-2 py-2">
                      <Link href={`/backtests/results/${run.id}`}>
                        <Button className="px-3">Aç</Button>
                      </Link>
                      <Button className="bg-danger px-3" onClick={() => remove(run.id)}><Trash2 size={16} /></Button>
                    </td>
                  </tr>
                ))}
                {runs.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted" colSpan={8}>Henüz backtest yok.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </section>
    </main>
  );
}
