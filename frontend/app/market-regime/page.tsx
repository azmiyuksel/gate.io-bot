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

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LastUpdated } from "@/components/ui/last-updated";
import { getAccessToken } from "@/lib/auth-api";
import { money } from "@/lib/utils";
import { useToast } from "@/components/ui/toast";
import {
  getCurrentRegime,
  getRegimeHistory,
  getRegimePerformance,
  getRegimeTransitions,
  recalculateRegime,
} from "@/lib/regime-api";
import type { RegimePerformance, RegimeStatus, RegimeTransition } from "@/types/regime";

const REGIME_COLORS: Record<string, string> = {
  TRENDING_BULL: "#146c5d",     // Emerald
  TRENDING_BEAR: "#b42318",     // Rose/Red
  SIDEWAYS: "#6b7280",          // Slate/Gray
  HIGH_VOLATILITY: "#d97706",   // Amber
  LOW_VOLATILITY: "#7c3aed",    // Violet
  BREAKOUT_PHASE: "#2563eb",    // Blue
};

const REGIME_LABELS: Record<string, string> = {
  TRENDING_BULL: "Yükseliş Trendi (Bull)",
  TRENDING_BEAR: "Düşüş Trendi (Bear)",
  SIDEWAYS: "Yatay Piyasa (Sideways)",
  HIGH_VOLATILITY: "Yüksek Volatilite",
  LOW_VOLATILITY: "Düşük Volatilite (Sıkışma)",
  BREAKOUT_PHASE: "Kırılım Aşaması (Breakout)",
};

export default function MarketRegimePage() {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [currentRegime, setCurrentRegime] = useState<RegimeStatus | null>(null);
  const [history, setHistory] = useState<RegimeStatus[]>([]);
  const [performance, setPerformance] = useState<RegimePerformance[]>([]);
  const [transitions, setTransitions] = useState<RegimeTransition[]>([]);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [curr, hist, perf, trans] = await Promise.all([
        getCurrentRegime(),
        getRegimeHistory(),
        getRegimePerformance(),
        getRegimeTransitions(),
      ]);
      if (curr) setCurrentRegime(curr);
      setHistory(hist);
      setPerformance(perf);
      setTransitions(trans);
      setLastUpdated(new Date());
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    refresh();
    intervalRef.current = setInterval(refresh, 10000); // 10s auto refresh
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [token, refresh]);

  async function handleRecalculate() {
    setActionLoading(true);
        const success = await recalculateRegime();
    if (success) {
      toast("Piyasa rejimi geçmişi başarıyla hesaplandı ve modeller eğitildi!", "success");
      await refresh();
    } else {
      toast("Piyasa rejimi hesaplama başarısız oldu.", "error");
    }
    setActionLoading(false);
  }

  // Format confidence history chart data
  const confidenceChartData = history.map((h) => ({
    time: new Date(h.created_at).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
    confidence: Number(h.confidence) * 100,
  })).reverse();

  // Aggregate regime distribution pie chart data
  const distributionMap: Record<string, number> = {};
  history.forEach((h) => {
    distributionMap[h.regime_type] = (distributionMap[h.regime_type] || 0) + 1;
  });
  const pieData = Object.entries(distributionMap).map(([name, value]) => ({
    name: REGIME_LABELS[name] || name,
    value,
    regimeKey: name,
  }));

  const activeRegime = currentRegime?.regime_type ?? "SIDEWAYS";
  const confidenceScore = Number(currentRegime?.confidence ?? 1.0);

  // Status Action text based on confidence and regime
  let statusText = "Güvenli İşlem (Normal)";
  let statusColor = "text-primary";
  if (confidenceScore < 0.5) {
    statusText = "İşlem Engellendi (Zayıf Güven)";
    statusColor = "text-danger font-bold";
  } else if (confidenceScore <= 0.7) {
    statusText = "Düşük Risk Modu (%50 Pozisyon)";
    statusColor = "text-amber-600 font-semibold";
  } else if (activeRegime === "HIGH_VOLATILITY") {
    statusText = "Yüksek Volatilite Koruması (%50 Pozisyon)";
    statusColor = "text-amber-600 font-semibold";
  }

  return (
    <main className="min-h-screen">
      {/* ─── Header ─── */}
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <Breadcrumb items={[{ label: "Piyasa Rejimi" }]} />
            <h1 className="text-xl font-semibold">Piyasa Rejim Analizi (Market Regime)</h1>
            <p className="text-sm text-muted">Makine öğrenimi ve kurallı analiz ile piyasa koşulu tespiti</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <LastUpdated time={lastUpdated} />
            <Button onClick={refresh} disabled={loading || !token}>
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} /> Yenile
            </Button>
          </div>
        </div>
        {token && (
          <div className="mx-auto flex max-w-7xl gap-2 px-6 pb-4">
            <Button onClick={handleRecalculate} disabled={actionLoading}>
              <Zap size={15} /> Modelleri Yeniden Eğit / Hesapla
            </Button>
          </div>
        )}
      </header>

      {/* ─── Metrics Grid ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <div className="mb-2 text-sm text-muted">Mevcut Piyasa Rejimi</div>
          <div className="flex items-center gap-2">
            <span
              className="h-3 w-3 rounded-full animate-pulse"
              style={{ backgroundColor: REGIME_COLORS[activeRegime] ?? "#6b7280" }}
            />
            <span className="text-lg font-bold" style={{ color: REGIME_COLORS[activeRegime] ?? "#6b7280" }}>
              {REGIME_LABELS[activeRegime] ?? activeRegime}
            </span>
          </div>
        </Card>

        <Card>
          <div className="mb-2 text-sm text-muted">Tahmin Güven Skoru (Confidence)</div>
          <div className="text-2xl font-bold">{`${(confidenceScore * 100).toFixed(0)}%`}</div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-border">
            <div
              className="h-1.5 rounded-full transition-all"
              style={{
                width: `${confidenceScore * 100}%`,
                backgroundColor: confidenceScore < 0.5 ? "#b42318" : confidenceScore <= 0.7 ? "#d97706" : "#146c5d"
              }}
            />
          </div>
        </Card>

        <Card>
          <div className="mb-2 text-sm text-muted">Strateji / Risk Filtre Durumu</div>
          <div className={`text-base font-semibold ${statusColor}`}>{statusText}</div>
        </Card>

        <Card>
          <div className="mb-2 text-sm text-muted">Regime Bazlı Risk Çarpanı</div>
          <div className="text-2xl font-bold">
            {activeRegime === "HIGH_VOLATILITY" ? "0.50x" : activeRegime === "SIDEWAYS" ? "0.70x" : activeRegime === "LOW_VOLATILITY" ? "1.20x" : activeRegime === "BREAKOUT_PHASE" ? "1.10x" : "1.00x"}
          </div>
        </Card>
      </section>

      {/* ─── Row 1: Charts ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 sm:grid-cols-2 lg:grid-cols-[2fr_1fr]">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Regime Tahmin Güven Geçmişi</h2>
            <span className="text-sm text-muted">Konsensüs yüzdesi</span>
          </div>
          <div className="h-72">
            {confidenceChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={confidenceChartData}>
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} domain={[0, 100]} />
                  <Tooltip formatter={(v: number) => `${v.toFixed(0)}%`} />
                  <Area type="monotone" dataKey="confidence" stroke="#146c5d" fill="#146c5d33" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">Tahmin geçmişi bulunmuyor.</div>
            )}
          </div>
        </Card>

        <Card>
          <h2 className="mb-4 text-base font-semibold">Piyasa Rejim Dağılımı</h2>
          <div className="flex h-72 items-center justify-center">
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={REGIME_COLORS[entry.regimeKey] ?? "#6b7280"} />
                    ))}
                  </Pie>
                  <Tooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-sm text-muted">Veri bulunmuyor.</div>
            )}
          </div>
        </Card>
      </section>

      {/* ─── Row 2: Strategy performance per regime ─── */}
      <section className="mx-auto max-w-7xl px-6 pb-6">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Rejim Bazlı Strateji Performans Matrisi</h2>
          <div className="overflow-x-auto">
            <table role="table" className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th scope="col" className="py-2">Piyasa Rejimi</th>
                  <th scope="col">Strateji</th>
                  <th scope="col">Toplam İşlem</th>
                  <th scope="col">Kazanma Oranı (Win Rate)</th>
                  <th scope="col">Profit Factor</th>
                  <th scope="col">Toplam PnL</th>
                  <th scope="col">Maks Drawdown</th>
                </tr>
              </thead>
              <tbody>
                {performance.map((perf) => {
                  const pnl = Number(perf.total_pnl);
                  const winRate = perf.total_trades > 0 ? (perf.winning_trades / perf.total_trades) * 100 : 0;
                  return (
                    <tr key={perf.id} className="border-b border-border">
                      <td className="py-3 font-semibold" style={{ color: REGIME_COLORS[perf.regime_type] ?? "#6b7280" }}>
                        {REGIME_LABELS[perf.regime_type] ?? perf.regime_type}
                      </td>
                      <td>{perf.strategy_name}</td>
                      <td>{perf.total_trades}</td>
                      <td>{winRate.toFixed(1)}%</td>
                      <td>{Number(perf.profit_factor).toFixed(2)}</td>
                      <td className={pnl >= 0 ? "text-primary font-medium" : "text-danger font-medium"}>
                        ${money(pnl)}
                      </td>
                      <td className="text-danger">{(Number(perf.drawdown) * 100).toFixed(2)}%</td>
                    </tr>
                  );
                })}
                {performance.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted text-center" colSpan={7}>
                      Strateji performans verisi bulunmuyor.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </section>

      {/* ─── Row 3: Votes breakdown & Transitions ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-10 sm:grid-cols-2 lg:grid-cols-[1fr_1fr]">
        {/* Model Votes Breakdown */}
        <Card>
          <h2 className="mb-4 text-base font-semibold">Ensemble Model Karar Dağılımı</h2>
          <div className="space-y-4">
            <div className="flex items-center justify-between rounded-lg border border-border p-3 bg-slate-50">
              <div>
                <p className="text-xs font-semibold text-muted">Rule-Based Sistem (Ağırlık: 40%)</p>
                <p className="text-sm font-bold" style={{ color: REGIME_COLORS[currentRegime?.rule_based_vote ?? ""] ?? "#6b7280" }}>
                  {REGIME_LABELS[currentRegime?.rule_based_vote ?? ""] ?? (currentRegime?.rule_based_vote ?? "Sideways")}
                </p>
              </div>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border p-3 bg-slate-50">
              <div>
                <p className="text-xs font-semibold text-muted">K-Means İstatiksel Kümeleme (Ağırlık: 30%)</p>
                <p className="text-sm font-bold" style={{ color: REGIME_COLORS[currentRegime?.clustering_vote ?? ""] ?? "#6b7280" }}>
                  {REGIME_LABELS[currentRegime?.clustering_vote ?? ""] ?? (currentRegime?.clustering_vote ?? "Sideways")}
                </p>
              </div>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border p-3 bg-slate-50">
              <div>
                <p className="text-xs font-semibold text-muted">Random Forest Sınıflandırıcı (Ağırlık: 30%)</p>
                <p className="text-sm font-bold" style={{ color: REGIME_COLORS[currentRegime?.ml_vote ?? ""] ?? "#6b7280" }}>
                  {REGIME_LABELS[currentRegime?.ml_vote ?? ""] ?? (currentRegime?.ml_vote ?? "Sideways")}
                </p>
              </div>
            </div>
          </div>
        </Card>

        {/* Transition Timeline Log */}
        <Card>
          <h2 className="mb-4 text-base font-semibold">Rejim Geçiş Günlüğü (Transition Timeline)</h2>
          <div className="overflow-y-auto max-h-[220px]">
            <table role="table" className="w-full text-left text-xs">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th scope="col" className="py-2">Zaman</th>
                  <th scope="col">Eski Rejim</th>
                  <th scope="col">Yeni Rejim</th>
                  <th scope="col">Güven</th>
                </tr>
              </thead>
              <tbody>
                {transitions.map((t) => (
                  <tr key={t.id} className="border-b border-border">
                    <td className="py-3 text-muted">
                      {new Date(t.created_at).toLocaleString("tr-TR")}
                    </td>
                    <td className="font-semibold text-muted">
                      {t.old_regime.replace("TRENDING_", "")}
                    </td>
                    <td className="font-semibold" style={{ color: REGIME_COLORS[t.new_regime] }}>
                      {t.new_regime.replace("TRENDING_", "")}
                    </td>
                    <td className="text-muted">{`${(Number(t.confidence) * 100).toFixed(0)}%`}</td>
                  </tr>
                ))}
                {transitions.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted text-center" colSpan={4}>
                      Yakın zamanda geçiş gerçekleşmedi.
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
