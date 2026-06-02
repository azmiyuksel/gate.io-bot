"use client";

import Link from "next/link";
import { Activity, Play, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { authFetch, getAccessToken } from "@/lib/auth-api";
import type { WalkForwardListItem } from "@/types/walkforward";

export function WalkForwardDashboard() {
  const [token, setToken] = useState("");
  const [runs, setRuns] = useState<WalkForwardListItem[]>([]);
  const [symbol, setSymbol] = useState("BTC_USDT");

  async function refresh() {
    if (!token) return;
    const response = await authFetch(`/walkforward`);
    if (response.ok) setRuns(await response.json());
  }

  async function start() {
    const response = await authFetch(`/walkforward/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol,
        timeframe: "1h",
        mode: "rolling",
        start_at: "2022-01-01T00:00:00Z",
        end_at: "2025-12-31T23:59:59Z",
        train_period_days: 365,
        test_period_days: 90,
        step_days: 90,
        n_trials: 30,
        data_source: "cache",
      }),
    });
    if (response.ok) await refresh();
  }

  async function remove(id: number) {
    await authFetch(`/walkforward/${id}`, { method: "DELETE" });
    await refresh();
  }

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  useEffect(() => {
    refresh();
  }, [token]);

  const latest = runs[0];

  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold">Walk-Forward Analysis</h1>
            <p className="text-sm text-muted">Out-of-sample dayanıklılık ve overfit kontrol paneli</p>
          </div>
          <div className="flex items-center gap-3">
            <Input className="w-32" value={symbol} onChange={(event) => setSymbol(event.target.value)} />
            <Button onClick={start}><Play size={16} /> Başlat</Button>
            <Button onClick={refresh}><Activity size={16} /> Yenile</Button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 lg:grid-cols-5">
        <Metric label="Robustness" value={(latest?.robustness_score ?? 0).toFixed(1)} />
        <Metric label="WFE" value={`${((latest?.wfe ?? 0) * 100).toFixed(1)}%`} />
        <Metric label="Consistency" value={`${((latest?.consistency_score ?? 0) * 100).toFixed(1)}%`} />
        <Metric label="Avg Sharpe" value={(latest?.average_sharpe ?? 0).toFixed(2)} />
        <Metric label="Avg Drawdown" value={`${((latest?.average_drawdown ?? 0) * 100).toFixed(2)}%`} />
      </section>

      <section className="mx-auto max-w-7xl px-6 pb-10">
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2">Tarih</th>
                  <th>Sembol</th>
                  <th>Mode</th>
                  <th>Robustness</th>
                  <th>WFE</th>
                  <th>Consistency</th>
                  <th>Karar</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className="border-b border-border">
                    <td className="py-3">{new Date(run.created_at).toLocaleString()}</td>
                    <td>{run.symbol} · {run.timeframe}</td>
                    <td>{run.mode}</td>
                    <td>{run.robustness_score.toFixed(1)}</td>
                    <td>{(run.wfe * 100).toFixed(1)}%</td>
                    <td>{(run.consistency_score * 100).toFixed(1)}%</td>
                    <td>{run.deployment_decision}</td>
                    <td className="flex justify-end gap-2 py-2">
                      <Link href={`/walk-forward/${run.id}`}><Button className="px-3">Detay</Button></Link>
                      <Button className="bg-danger px-3" onClick={() => remove(run.id)}><Trash2 size={16} /></Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <Card><div className="text-sm text-muted">{label}</div><div className="mt-2 text-2xl font-semibold">{value}</div></Card>;
}
