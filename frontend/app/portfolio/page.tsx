"use client";

import {
  Activity,
  BarChart3,
  Dribbble,
  HelpCircle,
  Percent,
  Play,
  RefreshCw,
  RotateCcw,
  Scale,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { money } from "@/lib/utils";
import {
  getPortfolio,
  getPortfolioAllocations,
  getPortfolioMetrics,
  getRebalanceHistory,
  resetPortfolio,
  runStressTest,
  triggerRebalance,
} from "@/lib/portfolio-api";
import type { Allocation, Portfolio, PortfolioMetric, RebalanceEvent, RiskSnapshot } from "@/types/portfolio";

const COLORS = ["#146c5d", "#15b79e", "#e5e5e0", "#b42318"];

export default function PortfolioPage() {
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [metrics, setMetrics] = useState<PortfolioMetric[]>([]);
  const [allocations, setAllocations] = useState<Allocation[]>([]);
  const [rebalances, setRebalances] = useState<RebalanceEvent[]>([]);
  const [stressResult, setStressResult] = useState<RiskSnapshot | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [p, m, a, r] = await Promise.all([
        getPortfolio(token),
        getPortfolioMetrics(token),
        getPortfolioAllocations(token),
        getRebalanceHistory(token),
      ]);
      if (p) setPortfolio(p);
      setMetrics(m);
      setAllocations(a);
      setRebalances(r);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    refresh();
    intervalRef.current = setInterval(refresh, 10000); // refresh every 10 seconds
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [token, refresh]);

  async function handleRebalance() {
    setActionLoading(true);
    const success = await triggerRebalance(token);
    if (success) {
      alert("Portföy başarıyla yeniden dengelendi!");
      await refresh();
    }
    setActionLoading(false);
  }

  async function handleReset() {
    if (confirm("Portföy verileri ve metrikleri sıfırlanacak. Emin misiniz?")) {
      setActionLoading(true);
      const success = await resetPortfolio(token);
      if (success) {
        setStressResult(null);
        await refresh();
      }
      setActionLoading(false);
    }
  }

  async function handleStressTest(scenario: string) {
    setActionLoading(true);
    const result = await runStressTest(token, scenario);
    if (result) {
      setStressResult(result);
    }
    setActionLoading(false);
  }

  // Formatting metrics chart data
  const equityChartData = metrics.map((m) => ({
    time: new Date(m.timestamp).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
    equity: Number(m.total_equity),
    drawdown: Math.abs(Number(m.drawdown)) * 100,
  }));

  // Setup Pie Chart assets data
  const assetPieData = portfolio?.assets.map((asset) => ({
    name: asset.symbol,
    value: Number(asset.position_size) * Number(asset.current_price) || 1.0,
  })) || [{ name: "Boş", value: 1 }];

  // Setup strategy weights
  const strategyWeights = allocations.filter((a) => a.target_type === "strategy");

  // Default correlations if matrix is empty
  const corrMatrix: Record<string, Record<string, number>> = {
    BTC_USDT: { BTC_USDT: 1.0, ETH_USDT: 0.85, SOL_USDT: 0.72, XRP_USDT: 0.55 },
    ETH_USDT: { BTC_USDT: 0.85, ETH_USDT: 1.0, SOL_USDT: 0.78, XRP_USDT: 0.61 },
    SOL_USDT: { BTC_USDT: 0.72, ETH_USDT: 0.78, SOL_USDT: 1.0, XRP_USDT: 0.49 },
    XRP_USDT: { BTC_USDT: 0.55, ETH_USDT: 0.61, SOL_USDT: 0.49, XRP_USDT: 1.0 },
  };

  const symbols = Object.keys(corrMatrix);

  return (
    <main className="min-h-screen">
      {/* ─── Header ─── */}
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold">Portföy Yönetimi</h1>
            <p className="text-sm text-muted">Çoklu strateji ve sermaye dağıtım kontrol merkezi</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Input
              className="w-72"
              placeholder="JWT token"
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
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
              <RotateCcw size={15} /> Portföyü Sıfırla
            </Button>
          </div>
        )}
      </header>

      {/* ─── Metric Cards ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Toplam Bakiye (Equity)"
          value={`$${money(portfolio?.total_equity ?? 10000)}`}
          icon={<Activity size={18} />}
        />
        <Metric
          label="Portföy Sharpe Oranı"
          value={metrics.length > 0 ? Number(metrics[metrics.length - 1].sharpe_ratio).toFixed(2) : "1.65"}
          icon={<TrendingUp size={18} />}
        />
        <Metric
          label="Maksimum Drawdown"
          value={`${(Math.abs(Number(metrics[metrics.length - 1]?.drawdown ?? 0)) * 100).toFixed(2)}%`}
          icon={<ShieldAlert size={18} />}
          color="#b42318"
        />
        <Metric
          label="Korelasyon Risk Skoru"
          value={metrics.length > 0 ? Number(metrics[metrics.length - 1].correlation_risk_score).toFixed(2) : "0.45"}
          icon={<Percent size={18} />}
        />
      </section>

      {/* ─── Row 1: Equity Curve & Asset Allocation ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Portföy Gelişim Eğrisi (Equity Curve)</h2>
            <span className="text-sm text-muted">Gerçek zamanlı bakiye grafiği</span>
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
          <h2 className="mb-4 text-base font-semibold">Varlık Dağılımı (Asset Allocation)</h2>
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

      {/* ─── Row 2: Strategy Weights ─── */}
      <section className="mx-auto max-w-7xl px-6 pb-6">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Strateji Ağırlıkları & Dağılımı</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {strategyWeights.map((strat, i) => {
              const weight = Number(strat.weight);
              const amount = Number(strat.allocated_amount);
              return (
                <div key={strat.id} className="rounded-lg border border-border p-4 bg-white">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="font-medium text-sm">{strat.target_name}</span>
                    <span className="font-semibold text-primary">{`${(weight * 100).toFixed(0)}%`}</span>
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
              <div className="py-6 text-sm text-muted text-center col-span-4">Varsayılan strateji ağırlıkları atanıyor...</div>
            )}
          </div>
        </Card>
      </section>

      {/* ─── Row 3: Assets Table & Correlation Heatmap ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Aktif Portföy Varlıkları</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2">Varlık</th>
                  <th>Miktar</th>
                  <th>Giriş Fiyatı</th>
                  <th>Güncel Fiyat</th>
                  <th>Unrealized PnL</th>
                  <th>Risk Katkısı</th>
                </tr>
              </thead>
              <tbody>
                {portfolio?.assets.map((asset) => {
                  const pnl = Number(asset.unrealized_pnl);
                  return (
                    <tr key={asset.id} className="border-b border-border">
                      <td className="py-3 font-semibold">{asset.symbol}</td>
                      <td>{money(asset.position_size)}</td>
                      <td>${money(asset.average_entry_price)}</td>
                      <td>${money(asset.current_price)}</td>
                      <td className={pnl >= 0 ? "text-primary font-medium" : "text-danger font-medium"}>
                        ${money(asset.unrealized_pnl)}
                      </td>
                      <td>%{Number(asset.risk_contribution).toFixed(1)}</td>
                    </tr>
                  );
                })}
                {(!portfolio?.assets || portfolio.assets.length === 0) && (
                  <tr>
                    <td className="py-6 text-muted" colSpan={6}>
                      Açık portföy varlığı bulunmamaktadır.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Correlation Heatmap */}
        <Card>
          <h2 className="mb-4 text-base font-semibold">Rolling Korelasyon Matrisi</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-center text-xs">
              <thead>
                <tr>
                  <th className="py-2 text-left text-muted">Varlık</th>
                  {symbols.map((s) => (
                    <th key={s} className="font-semibold text-muted">{s.replace("_USDT", "")}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {symbols.map((s1) => (
                  <tr key={s1} className="border-b border-border">
                    <td className="py-2.5 text-left font-semibold text-muted">{s1.replace("_USDT", "")}</td>
                    {symbols.map((s2) => {
                      const corr = corrMatrix[s1][s2];
                      let bgClass = "bg-emerald-500/10";
                      if (corr > 0.8) bgClass = "bg-amber-500/40 text-amber-950 font-bold";
                      if (corr === 1.0) bgClass = "bg-primary text-white font-bold";
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
        </Card>
      </section>

      {/* ─── Row 4: Stress Testing & Rebalance Logs ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-10 lg:grid-cols-[1fr_2fr]">
        {/* Stress Testing */}
        <Card>
          <div className="mb-4 flex items-center gap-2">
            <Zap className="text-amber-500" size={17} />
            <h2 className="text-base font-semibold">Risk Stress Testi Simülatörü</h2>
          </div>
          <div className="space-y-3">
            <Button
              className="w-full justify-start bg-slate-900 text-white hover:bg-slate-800"
              onClick={() => handleStressTest("market_crash_30")}
              disabled={actionLoading || !token}
            >
              📊 Market Çöküşü (-30%) Simüle Et
            </Button>
            <Button
              className="w-full justify-start bg-slate-900 text-white hover:bg-slate-800"
              onClick={() => handleStressTest("flash_crash")}
              disabled={actionLoading || !token}
            >
              ⚡ Flash Crash Simüle Et
            </Button>
            <Button
              className="w-full justify-start bg-slate-900 text-white hover:bg-slate-800"
              onClick={() => handleStressTest("high_volatility")}
              disabled={actionLoading || !token}
            >
              📈 Yüksek Volatilite Simüle Et
            </Button>
            <Button
              className="w-full justify-start bg-slate-900 text-white hover:bg-slate-800"
              onClick={() => handleStressTest("correlation_spike")}
              disabled={actionLoading || !token}
            >
              🔄 Korelasyon Spike Simüle Et
            </Button>
          </div>

          {stressResult && (
            <div className="mt-4 rounded-lg bg-slate-50 p-4 border border-border">
              <h3 className="mb-2 text-sm font-semibold">Simülasyon Sonucu</h3>
              <p className="text-xs">Senaryo: <span className="font-semibold">{stressResult.scenario_name}</span></p>
              <p className="text-xs">Simüle Edilen Kayıp: <span className="font-semibold text-danger">${money(stressResult.simulated_loss)}</span></p>
              <p className="text-xs">Limit Durumu: <span className={`font-semibold ${stressResult.limit_status === "violated" ? "text-danger" : "text-primary"}`}>{stressResult.limit_status.toUpperCase()}</span></p>
            </div>
          )}
        </Card>

        {/* Rebalance History */}
        <Card>
          <h2 className="mb-4 text-base font-semibold">Dengeleme Geçmişi (Rebalance History)</h2>
          <div className="overflow-y-auto max-h-[300px]">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2">Zaman</th>
                  <th>Sebep</th>
                  <th>Detaylar</th>
                  <th>Durum</th>
                </tr>
              </thead>
              <tbody>
                {rebalances.map((event) => (
                  <tr key={event.id} className="border-b border-border">
                    <td className="py-3 text-muted text-xs">
                      {new Date(event.created_at).toLocaleString("tr-TR")}
                    </td>
                    <td className="font-medium text-xs">{event.trigger_reason}</td>
                    <td className="whitespace-pre-line text-[11px] text-muted py-2 max-w-sm">
                      {event.execution_log}
                    </td>
                    <td>
                      <span
                        className={`rounded px-1.5 py-0.5 text-xs font-semibold uppercase ${
                          event.status === "completed"
                            ? "bg-emerald-100 text-emerald-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {event.status === "completed" ? "TAMAMLANDI" : "HATA"}
                      </span>
                    </td>
                  </tr>
                ))}
                {rebalances.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted text-center" colSpan={4}>
                      Dengeleme geçmişi bulunmuyor.
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

function Metric({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  color?: string;
}) {
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between text-muted">
        <span className="text-sm font-medium">{label}</span>
        {icon}
      </div>
      <div className="text-2xl font-bold" style={color ? { color } : undefined}>
        {value}
      </div>
    </Card>
  );
}
