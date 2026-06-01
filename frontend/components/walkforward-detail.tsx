"use client";

import dynamic from "next/dynamic";
import { Download } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { money } from "@/lib/utils";
import type { WalkForwardDetail as WalkForwardDetailType } from "@/types/walkforward";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export function WalkForwardDetail({ id }: { id: string }) {
  const [token, setToken] = useState("");
  const [run, setRun] = useState<WalkForwardDetailType | null>(null);
  const [selectedWindow, setSelectedWindow] = useState<number | null>(null);

  async function refresh() {
    if (!token) return;
    const response = await fetch(`${apiUrl}/walkforward/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) {
      const data = await response.json();
      setRun(data);
      setSelectedWindow(data.windows[0]?.window_id ?? null);
    }
  }

  useEffect(() => {
    refresh();
  }, [token]);

  const charts = run?.report.charts ?? {};
  const equityFigure = useMemo(() => parseFigure(charts.combined_equity_curve), [charts]);
  const windowFigure = useMemo(() => parseFigure(charts.window_performance), [charts]);
  const window = run?.windows.find((item) => item.window_id === selectedWindow);

  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold">WFA Sonucu #{id}</h1>
            <p className="text-sm text-muted">{run ? `${run.symbol} · ${run.mode} · ${run.deployment_decision.decision}` : "JWT token gir ve sonucu yükle"}</p>
          </div>
          <div className="flex items-center gap-3">
            <Input className="w-80" placeholder="JWT token" type="password" value={token} onChange={(event) => setToken(event.target.value)} />
            <a href={`${apiUrl}/walkforward/${id}/report`}><Button><Download size={16} /> PDF</Button></a>
          </div>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 lg:grid-cols-5">
        <Metric label="Robustness" value={String(run?.aggregated_metrics.robustness_score ?? 0)} />
        <Metric label="WFE" value={`${Number(run?.aggregated_metrics.wfe ?? 0) * 100}%`} />
        <Metric label="Consistency" value={`${Number(run?.aggregated_metrics.consistency_score ?? 0) * 100}%`} />
        <Metric label="VaR 95" value={`${((run?.monte_carlo_results.var_95 ?? 0) * 100).toFixed(2)}%`} />
        <Metric label="Ruin" value={`${((run?.monte_carlo_results.ruin_probability ?? 0) * 100).toFixed(2)}%`} />
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Combined Equity Curve</h2>
          {equityFigure ? <Plot data={equityFigure.data} layout={{ ...equityFigure.layout, autosize: true }} style={{ width: "100%", height: 320 }} /> : <p className="text-sm text-muted">Grafik yok.</p>}
        </Card>
        <Card>
          <h2 className="mb-4 text-base font-semibold">Window Performance</h2>
          {windowFigure ? <Plot data={windowFigure.data} layout={{ ...windowFigure.layout, autosize: true }} style={{ width: "100%", height: 320 }} /> : <p className="text-sm text-muted">Grafik yok.</p>}
        </Card>
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-10 lg:grid-cols-[1fr_2fr]">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Pencereler</h2>
          <div className="grid gap-2">
            {(run?.windows ?? []).map((item) => (
              <button key={item.window_id} className="rounded-md border border-border px-3 py-2 text-left text-sm" onClick={() => setSelectedWindow(item.window_id)}>
                Window {item.window_id} · WFE {(item.wfe * 100).toFixed(1)}%
              </button>
            ))}
          </div>
        </Card>
        <Card>
          <h2 className="mb-4 text-base font-semibold">Window Detail</h2>
          {window && (
            <div className="grid gap-4">
              <div className="grid gap-3 text-sm md:grid-cols-2">
                <Info label="Train Period" value={`${window.train_start} → ${window.train_end}`} />
                <Info label="Test Period" value={`${window.test_start} → ${window.test_end}`} />
                <Info label="Train Sharpe" value={window.train_metrics.sharpe_ratio?.toFixed(2) ?? "0"} />
                <Info label="Test Sharpe" value={window.test_metrics.sharpe_ratio?.toFixed(2) ?? "0"} />
                <Info label="Test Net Profit" value={`$${money(window.test_metrics.net_profit ?? 0)}`} />
                <Info label="Overfit" value={window.overfit_warning ? "OVERFIT_WARNING" : "Clear"} />
              </div>
              <pre className="overflow-auto rounded-md bg-background p-3 text-xs">{JSON.stringify(window.best_params, null, 2)}</pre>
            </div>
          )}
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

function Metric({ label, value }: { label: string; value: string }) {
  return <Card><div className="text-sm text-muted">{label}</div><div className="mt-2 text-2xl font-semibold">{value}</div></Card>;
}

function Info({ label, value }: { label: string; value: string }) {
  return <div><div className="text-muted">{label}</div><div className="font-medium">{value}</div></div>;
}
