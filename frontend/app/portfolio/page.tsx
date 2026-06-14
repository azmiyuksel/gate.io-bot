"use client";

import {
  Activity, Percent, RefreshCw, RotateCcw, Scale, ShieldAlert, TrendingUp, Zap,
} from "lucide-react";
import {
  Area, AreaChart, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { useCallback, useEffect, useRef, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { getAccessToken } from "@/lib/auth-api";
import { LastUpdated } from "@/components/ui/last-updated";
import { Metric } from "@/components/ui/metric";
import { money } from "@/lib/utils";
import {
  getPortfolio, getPortfolioAllocations, getPortfolioCorrelations,
  getPortfolioMetrics, getPortfolioVaR, getRebalanceHistory, getStrategyPerformance,
  resetPortfolio, runStressTest, triggerRebalance,
} from "@/lib/portfolio-api";
import { useToast } from "@/components/ui/toast";
import type {
  Allocation, Portfolio, PortfolioCorrelations,
  PortfolioMetric, RebalanceEvent, RiskSnapshot, StrategyPerformance,
} from "@/types/portfolio";

const COLORS = ["#146c5d", "#15b79e", "#e5e5e0", "#b42318"];

export default function PortfolioPage() {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [metrics, setMetrics] = useState<PortfolioMetric[]>([]);
  const [allocations, setAllocations] = useState<Allocation[]>([]);
  const [rebalances, setRebalances] = useState<RebalanceEvent[]>([]);
  const [stressResult, setStressResult] = useState<RiskSnapshot | null>(null);
  const [correlations, setCorrelations] = useState<PortfolioCorrelations | null>(null);
  const [varData, setVarData] = useState<{ var: number; cvar: number } | null>(null);
  const [strategyPerf, setStrategyPerf] = useState<StrategyPerformance[]>([]);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => { setToken(getAccessToken()); }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    const fetchErrors: string[] = [];
    try {
      const results = await Promise.allSettled([
        getPortfolio(),
        getPortfolioMetrics(),
        getPortfolioAllocations(),
        getRebalanceHistory(),
        getPortfolioCorrelations(),
        getPortfolioVaR(),
        getStrategyPerformance(),
      ]);
      const [p, m, a, r, c, v, sp] = results;
      if (p.status === "fulfilled" && p.value) setPortfolio(p.value);
      else if (p.status === "rejected") fetchErrors.push("Portfoy");
      if (m.status === "fulfilled") setMetrics(m.value);
      else if (m.status === "rejected") fetchErrors.push("Metrikler");
      if (a.status === "fulfilled") setAllocations(a.value);
      else if (a.status === "rejected") fetchErrors.push("Tahsisler");
      if (r.status === "fulfilled") setRebalances(r.value);
      else if (r.status === "rejected") fetchErrors.push("Dengeleme gecmisi");
      if (c.status === "fulfilled") setCorrelations(c.value);
      if (v.status === "fulfilled") setVarData(v.value);
      if (sp.status === "fulfilled") setStrategyPerf(sp.value);
      setLastUpdated(new Date());
    } finally {
      setLoading(false);
      if (fetchErrors.length > 0) {
        setErrors(fetchErrors);
        toast(`Bazi veriler alinamadi: ${fetchErrors.join(", ")}`, "error");
      } else {
        setErrors([]);
      }
    }
  }, [token, toast]);

  useEffect(() => {
    if (!token) return;
    refresh();
    intervalRef.current = setInterval(refresh, 30000);
    const onVisible = () => { refresh(); };
    const onHidden = () => { if (intervalRef.current) clearInterval(intervalRef.current); };
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") {
        onVisible();
        intervalRef.current = setInterval(refresh, 30000);
      } else {
        onHidden();
      }
    });
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [token, refresh]);

  async function handleRebalance() {
    setActionLoading(true);
    const success = await triggerRebalance();
    if (success) { toast("Portfoy basariyla yeniden dengelendi!", "success"); await refresh(); }
    setActionLoading(false);
  }

  async function handleReset() { setConfirmReset(true); }

  async function handleResetConfirm() {
    setActionLoading(true);
    const success = await resetPortfolio();
    if (success) { setStressResult(null); await refresh(); }
    setActionLoading(false);
  }

  async function handleStressTest(scenario: string) {
    setActionLoading(true);
    const result = await runStressTest(scenario);
    if (result) setStressResult(result);
    setActionLoading(false);
  }

  const equityChartData = metrics.map((m) => ({
    time: new Date(m.timestamp).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
    equity: m.total_equity,
  }));

  const drawdownChartData = metrics.map((m) => ({
    time: new Date(m.timestamp).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
    drawdown: Math.abs(m.drawdown) * 100,
  }));

  const assetPieData = portfolio?.assets.map((asset) => ({
    name: asset.symbol,
    value: asset.position_size * asset.current_price || 1.0,
  })) || [{ name: "Bos", value: 1 }];

  const strategyWeights = allocations.filter((a) => a.target_type === "strategy");
  const corrMatrix = correlations?.matrix ?? {};
  const symbols = correlations?.symbols ?? [];
  const hasCorrData = Boolean(correlations?.data_available && symbols.length >= 2);

  const liveDrawdown = portfolio && portfolio.peak_equity > 0 && portfolio.total_equity < portfolio.peak_equity
    ? ((portfolio.peak_equity - portfolio.total_equity) / portfolio.peak_equity) * 100
    : 0;

  const investedPct = portfolio && portfolio.total_equity > 0
    ? ((portfolio.total_equity - portfolio.cash_balance) / portfolio.total_equity) * 100
    : 0;

  const rebalanceStatusLabel = (status: string) => {
    if (status === "completed") return { text: "TAMAMLANDI", cls: "bg-emerald-100 text-emerald-700" };
    if (status === "skipped") return { text: "ATLANDI", cls: "bg-amber-100 text-amber-700" };
    return { text: "HATA", cls: "bg-red-100 text-red-700" };
  };

  return (
    <main className="min-h-screen">
      <ConfirmDialog
        open={confirmReset}
        title="Portfoyu Sifirla"
        message="Portfoy verileri ve metrikleri sifirlanacak. Emin misiniz?"
        confirmLabel="Sifirla"
        danger
        onConfirm={handleResetConfirm}
        onCancel={() => setConfirmReset(false)}
      />
      {/* --- Header --- */}
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <Breadcrumb items={[{ label: "Portfoy" }]} />
            <h1 className="text-xl font-semibold">Portfoy Yonetimi</h1>
            <p className="text-sm text-muted">Coklu strateji ve sermaye dagitim kontrol merkezi</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <LastUpdated time={lastUpdated} />
            {errors.length > 0 && (
              <span className="text-xs text-danger font-medium" title={errors.join(", ")}>
                Kismi hata ({errors.length})
              </span>
            )}
            <Button onClick={refresh} disabled={loading || !token}>
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} /> Yenile
            </Button>
          </div>
        </div>
        {token && (
          <div className="mx-auto flex max-w-7xl gap-2 px-6 pb-4">
            <Button onClick={handleRebalance} disabled={actionLoading}>
              <Scale size={15} /> Yeniden Dengele
            </Button>
            <Button onClick={handleReset} disabled={actionLoading} className="bg-danger">
              <RotateCcw size={15} /> Portfoyu Sifirla
            </Button>
          </div>
        )}
      </header>

      {/* --- Metric Cards (2 rows) --- */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Toplam Bakiye (Equity)"
          value={`$${money(portfolio?.total_equity ?? 10000)}`}
          icon={<Activity size={18} />}
        />
        <Metric
          label="Portfoy Sharpe Orani"
          value={metrics.length > 0 ? metrics[metrics.length - 1].sharpe_ratio.toFixed(2) : "-"}
          icon={<TrendingUp size={18} />}
        />
        <Metric
          label="Maksimum Drawdown"
          value={`${liveDrawdown.toFixed(2)}%`}
          icon={<ShieldAlert size={18} />}
          color="#b42318"
        />
        <Metric
          label="Korelasyon Risk Skoru"
          value={metrics.length > 0 ? metrics[metrics.length - 1].correlation_risk_score.toFixed(2) : "-"}
          icon={<Percent size={18} />}
        />
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Nakit Bakiye"
          value={`$${money(portfolio?.cash_balance ?? 0)}`}
          icon={<Activity size={18} />}
        />
        <Metric
          label="Yatirim Orani"
          value={`${investedPct.toFixed(1)}%`}
          icon={<TrendingUp size={18} />}
        />
        <Metric
          label="VaR %95 (Tarihsel)"
          value={varData ? `${(varData.var * 100).toFixed(2)}%` : "-"}
          icon={<ShieldAlert size={18} />}
          color="#b42318"
        />
        <Metric
          label="Volatility-Adj. Return"
          value={metrics.length > 0 ? metrics[metrics.length - 1].volatility_adjusted_return.toFixed(2) : "-"}
          icon={<Percent size={18} />}
        />
      </section>

      {/* --- Row 1: Equity Curve & Asset Allocation --- */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Portfoy Gelisim Egrisi (Equity Curve)</h2>
            <span className="text-sm text-muted">Gercek zamanli bakiye grafigi</span>
          </div>
          <div className="h-72">
            {equityChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityChartData}>
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
                  <Tooltip formatter={(v: number) => `$${money(v)}`} />
                  <Area type="monotone" dataKey="equity" stroke="#146c5d" fill="#146c5d33" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">Equity verisi bulunmuyor.</div>
            )}
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-base font-semibold">Varlik Dagilimi (Asset Allocation)</h2>
          <div className="flex h-72 items-center justify-center">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={assetPieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {assetPieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number) => `$${money(v)}`} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </section>

      {/* --- Row 2: Drawdown overlay chart --- */}
      <section className="mx-auto max-w-7xl px-6 pb-6">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Drawdown Egrisi (%)</h2>
            <span className="text-sm text-muted">Tarihsel cekilme grafigi</span>
          </div>
          <div className="h-48">
            {drawdownChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={drawdownChartData}>
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
                  <Tooltip formatter={(v: number) => `${v.toFixed(2)}%`} />
                  <Area type="monotone" dataKey="drawdown" stroke="#b42318" fill="#b4231833" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">Drawdown verisi bulunmuyor.</div>
            )}
          </div>
        </Card>
      </section>

      {/* --- Row 3: Strategy Weights & Performance --- */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Strateji Agirliklari & Dagilimi</h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {strategyWeights.map((strat) => {
              const weight = strat.weight;
              const amount = strat.allocated_amount;
              return (
                <div key={strat.id} className="rounded-lg border border-border p-4 bg-white">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="font-medium text-sm">{strat.target_name}</span>
                    <span className="font-semibold text-primary">{(weight * 100).toFixed(0)}%</span>
                  </div>
                  <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-border">
                    <div
                      className="h-2 rounded-full bg-primary transition-all"
                      style={{ width: `${weight * 100}%` }}
                    />
                  </div>
                  <p className="text-xs text-muted">Tahsis Edilen: ${money(amount)}</p>
                </div>
              );
            })}
            {strategyWeights.length === 0 && (
              <div className="py-6 text-sm text-muted text-center col-span-2">Varsayilan strateji agirliklari ataniyor...</div>
            )}
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-base font-semibold">Strateji Performans Metrikleri</h2>
          {strategyPerf.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border text-muted">
                  <tr>
                    <th scope="col" className="py-2">Strateji</th>
                    <th scope="col">Sharpe</th>
                    <th scope="col">Win Rate</th>
                    <th scope="col">Profit Faktor</th>
                    <th scope="col">Max DD</th>
                    <th scope="col">Stabilite</th>
                  </tr>
                </thead>
                <tbody>
                  {strategyPerf.map((sp) => (
                    <tr key={sp.name} className="border-b border-border">
                      <td className="py-2.5 font-medium">{sp.name}</td>
                      <td className={sp.sharpe_ratio >= 0 ? "text-primary" : "text-danger"}>
                        {sp.sharpe_ratio.toFixed(2)}
                      </td>
                      <td>{(sp.win_rate * 100).toFixed(0)}%</td>
                      <td>{sp.profit_factor.toFixed(2)}</td>
                      <td className="text-danger">{(sp.max_drawdown * 100).toFixed(1)}%</td>
                      <td>{sp.stability_score.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="py-6 text-sm text-muted text-center">Henuz kapali islem verisi yok.</p>
          )}
        </Card>
      </section>

      {/* --- Row 4: Assets Table & Correlation Heatmap --- */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Aktif Portfoy Varliklari</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th scope="col" className="py-2">Varlik</th>
                  <th scope="col">Miktar</th>
                  <th scope="col">Giris Fiyati</th>
                  <th scope="col">Guncel Fiyat</th>
                  <th scope="col">Unrealized PnL</th>
                  <th scope="col">Risk Katkisi</th>
                </tr>
              </thead>
              <tbody>
                {portfolio?.assets.map((asset) => {
                  const pnl = asset.unrealized_pnl;
                  return (
                    <tr key={asset.id} className="border-b border-border">
                      <td className="py-3 font-semibold">{asset.symbol}</td>
                      <td>{money(asset.position_size)}</td>
                      <td>${money(asset.average_entry_price)}</td>
                      <td>${money(asset.current_price)}</td>
                      <td className={pnl >= 0 ? "text-primary font-medium" : "text-danger font-medium"}>
                        ${money(asset.unrealized_pnl)}
                      </td>
                      <td>%{asset.risk_contribution.toFixed(1)}</td>
                    </tr>
                  );
                })}
                {(!portfolio?.assets || portfolio.assets.length === 0) && (
                  <tr>
                    <td className="py-6 text-muted" colSpan={6}>
                      Acik portfoy varligi bulunmamaktadir.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Correlation Heatmap */}
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Getiri Korelasyon Matrisi</h2>
            {correlations?.timeframe && (
              <span className="text-xs text-muted">{correlations.timeframe} / getiriler</span>
            )}
          </div>
          {!hasCorrData ? (
            <p className="py-8 text-center text-sm text-muted">
              Korelasyon icin yeterli gecmis veri yok. Market-data toplandikca
              (en az ~10 mum/sembol) matris otomatik dolacak.
            </p>
          ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-center text-xs">
              <thead>
                <tr>
                  <th scope="col" className="py-2 text-left text-muted">Varlik</th>
                  {symbols.map((s) => (
                    <th scope="col" key={s} className="font-semibold text-muted">{s.replace("_USDT", "")}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {symbols.map((s1) => (
                  <tr key={s1} className="border-b border-border">
                    <td className="py-2.5 text-left font-semibold text-muted">{s1.replace("_USDT", "")}</td>
                    {symbols.map((s2) => {
                      const isDiagonal = s1 === s2;
                      const corr = isDiagonal ? 1.0 : (corrMatrix[s1]?.[s2] ?? 0);
                      let bgClass = "bg-emerald-500/10";
                      if (corr > 0.8) bgClass = "bg-amber-500/40 text-amber-950 font-bold";
                      if (isDiagonal) bgClass = "bg-slate-200 font-bold";
                      return (
                        <td key={s2} className={`rounded p-1 ${bgClass}`}>
                          {corr.toFixed(2)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          )}
        </Card>
      </section>

      {/* --- Row 5: Stress Testing & Rebalance Logs --- */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-10 lg:grid-cols-[1fr_2fr]">
        {/* Stress Testing */}
        <Card>
          <div className="mb-4 flex items-center gap-2">
            <Zap className="text-amber-500" size={17} />
            <h2 className="text-base font-semibold">Risk Stress Testi Simulatoru</h2>
          </div>
          <div className="space-y-3">
            <Button
              className="w-full justify-start bg-slate-900 text-white hover:bg-slate-800"
              onClick={() => handleStressTest("market_crash_30")}
              disabled={actionLoading || !token}
            >
              Market Cokusu (-30%) Simule Et
            </Button>
            <Button
              className="w-full justify-start bg-slate-900 text-white hover:bg-slate-800"
              onClick={() => handleStressTest("flash_crash")}
              disabled={actionLoading || !token}
            >
              Flash Crash Simule Et
            </Button>
            <Button
              className="w-full justify-start bg-slate-900 text-white hover:bg-slate-800"
              onClick={() => handleStressTest("high_volatility")}
              disabled={actionLoading || !token}
            >
              Yuksek Volatilite Simule Et
            </Button>
            <Button
              className="w-full justify-start bg-slate-900 text-white hover:bg-slate-800"
              onClick={() => handleStressTest("correlation_spike")}
              disabled={actionLoading || !token}
            >
              Korelasyon Spike Simule Et
            </Button>
          </div>

          {stressResult && (
            <div className="mt-4 rounded-lg bg-slate-50 p-4 border border-border">
              <h3 className="mb-2 text-sm font-semibold">Simulasyon Sonucu</h3>
              <p className="text-xs">Senaryo: <span className="font-semibold">{stressResult.scenario_name}</span></p>
              <p className="text-xs">Simule Edilen Kayip: <span className="font-semibold text-danger">${money(stressResult.simulated_loss)}</span></p>
              <p className="text-xs">Limit Durumu: <span className={`font-semibold ${stressResult.limit_status === "violated" ? "text-danger" : "text-primary"}`}>{stressResult.limit_status.toUpperCase()}</span></p>
            </div>
          )}
        </Card>

        {/* Rebalance History */}
        <Card>
          <h2 className="mb-4 text-base font-semibold">Dengeleme Gecmisi (Rebalance History)</h2>
          <div className="overflow-y-auto max-h-[300px]">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th scope="col" className="py-2">Zaman</th>
                  <th scope="col">Sebep</th>
                  <th scope="col">Agirlik Degisimi</th>
                  <th scope="col">Detaylar</th>
                  <th scope="col">Durum</th>
                </tr>
              </thead>
              <tbody>
                {rebalances.map((event) => {
                  const prev = event.previous_weights ?? {};
                  const next = event.new_weights ?? {};
                  const deltas: string[] = [];
                  for (const name of new Set([...Object.keys(prev), ...Object.keys(next)])) {
                    const diff = (next[name] ?? 0) - (prev[name] ?? 0);
                    if (diff !== 0) {
                      deltas.push(`${name}: ${diff > 0 ? "+" : ""}${(diff * 100).toFixed(0)}%`);
                    }
                  }
                  const status = rebalanceStatusLabel(event.status);
                  return (
                    <tr key={event.id} className="border-b border-border">
                      <td className="py-3 text-muted text-xs">
                        {new Date(event.created_at).toLocaleString("tr-TR")}
                      </td>
                      <td className="font-medium text-xs">{event.trigger_reason}</td>
                      <td className="text-xs whitespace-nowrap">
                        {deltas.length > 0
                          ? deltas.map((d, i) => (
                              <span key={i} className={`mr-1 rounded px-1 py-0.5 text-xs font-medium ${
                                d.includes("+") ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
                              }`}>{d}</span>
                            ))
                          : "-"
                        }
                      </td>
                      <td className="whitespace-pre-line text-xs text-muted py-2 max-w-sm">
                        {event.execution_log}
                      </td>
                      <td>
                        <span className={`rounded px-1.5 py-0.5 text-xs font-semibold uppercase ${status.cls}`}>
                          {status.text}
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {rebalances.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted text-center" colSpan={5}>
                      Dengeleme gecmisi bulunmuyor.
                    </td>
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
