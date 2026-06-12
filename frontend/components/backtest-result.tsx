"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowLeft, Download, GitBranch, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Metric } from "@/components/ui/metric";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { useToast } from "@/components/ui/toast";
import { money } from "@/lib/utils";
import { authFetch, getAccessToken } from "@/lib/auth-api";
import type { BacktestDetail } from "@/types/backtest";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export function BacktestResult({ id }: { id: string }) {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [run, setRun] = useState<BacktestDetail | null>(null);

  async function refresh() {
    if (!token) return;
    const response = await authFetch(`/backtests/${id}`);
    if (response.ok) setRun(await response.json());
  }

  async function optimize() {
    const res = await authFetch(`/backtests/${id}/optimize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (res.ok) {
      toast("Optimizasyon başlatıldı", "success");
      await refresh();
    } else {
      toast("Optimizasyon başlatılamadı", "error");
    }
  }

  async function walkForward() {
    const res = await authFetch(`/backtests/${id}/walk-forward`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (res.ok) {
      toast("Walk-forward başlatıldı", "success");
      await refresh();
    } else {
      toast("Walk-forward başlatılamadı", "error");
    }
  }

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  useEffect(() => {
    refresh();
  }, [token]);

  const equityFigure = useMemo(() => parseFigure(run?.charts.equity_curve), [run]);
  const drawdownFigure = useMemo(() => parseFigure(run?.charts.drawdown_curve), [run]);

  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <Breadcrumb
              items={[
                { label: "Backtest", href: "/backtests" },
                { label: `Sonucu #${id}` },
              ]}
            />
            <h1 className="mt-2 text-xl font-semibold">Backtest Sonucu #{id}</h1>
            <p className="text-sm text-muted">
              {run ? `${run.symbol} · ${run.timeframe} · ${run.status}` : "Panelden giriş yapın ve sonucu yükleyin"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/backtests">
              <Button className="bg-transparent text-foreground hover:bg-border/60">
                <ArrowLeft size={16} /> Geri
              </Button>
            </Link>
            <Button onClick={optimize}><SlidersHorizontal size={16} /> Optimize</Button>
            <Button onClick={walkForward}><GitBranch size={16} /> Walk Forward</Button>
            <a href={`${apiUrl}/backtests/${id}/report.pdf`}>
              <Button><Download size={16} /> PDF</Button>
            </a>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Net Kar" value={`$${money(run?.metrics.net_profit ?? 0)}`} />
        <Metric label="Sharpe" value={(run?.metrics.sharpe_ratio ?? 0).toFixed(2)} />
        <Metric label="Max DD" value={`${((run?.metrics.max_drawdown ?? 0) * 100).toFixed(2)}%`} />
        <Metric label="Win Rate" value={`${((run?.metrics.win_rate ?? 0) * 100).toFixed(1)}%`} />
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Equity Curve</h2>
          {equityFigure ? (
            <Plot data={equityFigure.data} layout={{ ...equityFigure.layout, autosize: true }} style={{ width: "100%", height: 320 }} />
          ) : (
            <p className="text-sm text-muted">Grafik yok.</p>
          )}
        </Card>
        <Card>
          <h2 className="mb-4 text-base font-semibold">Drawdown Curve</h2>
          {drawdownFigure ? (
            <Plot data={drawdownFigure.data} layout={{ ...drawdownFigure.layout, autosize: true }} style={{ width: "100%", height: 320 }} />
          ) : (
            <p className="text-sm text-muted">Grafik yok.</p>
          )}
        </Card>
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-10 lg:grid-cols-[2fr_1fr]">
        <Card>
          <h2 className="mb-4 text-base font-semibold">İşlem Listesi</h2>
          <div className="max-h-96 overflow-auto">
            <table className="w-full text-left text-sm" role="table">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2" scope="col">Giriş</th>
                  <th scope="col">Çıkış</th>
                  <th scope="col">Miktar</th>
                  <th scope="col">PnL</th>
                  <th scope="col">Neden</th>
                </tr>
              </thead>
              <tbody>
                {(run?.trades ?? []).map((trade) => (
                  <tr key={trade.id} className="border-b border-border">
                    <td className="py-2">{money(trade.entry_price)}</td>
                    <td>{money(trade.exit_price)}</td>
                    <td>{money(trade.quantity)}</td>
                    <td>{money(trade.pnl)}</td>
                    <td>{trade.exit_reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card>
          <h2 className="mb-4 text-base font-semibold">Risk Analizi</h2>
          <Risk label="Sortino" value={run?.metrics.sortino_ratio} />
          <Risk label="Calmar" value={run?.metrics.calmar_ratio} />
          <Risk label="Profit Factor" value={run?.metrics.profit_factor} />
          <Risk label="Worst Case MC" value={run?.monte_carlo_results.worst_case} percent />
          <Risk label="Ruin Probability" value={run?.monte_carlo_results.ruin_probability} percent />
        </Card>
      </section>
    </main>
  );
}

function parseFigure(raw?: string) {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as { data: never[]; layout: Record<string, unknown> };
  } catch {
    return null;
  }
}

function Risk({ label, value, percent = false }: { label: string; value?: number; percent?: boolean }) {
  const display = percent ? `${((value ?? 0) * 100).toFixed(2)}%` : (value ?? 0).toFixed(2);
  return (
    <div className="flex justify-between border-b border-border py-2 text-sm">
      <span className="text-muted">{label}</span>
      <span className="font-medium">{display}</span>
    </div>
  );
}
