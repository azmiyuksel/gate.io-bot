"use client";

import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRightLeft,
  CheckCircle2,
  HelpCircle,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { getAccessToken } from "@/lib/auth-api";
import { money } from "@/lib/utils";
import {
  getStrategyHealth,
  getHealthMetrics,
  getStrategyAlerts,
  recalculateStrategyHealth,
  pauseStrategy,
  resumeStrategy,
  getStrategyBaseline,
  getTransitions,
} from "@/lib/health-api";
import type {
  StrategyHealthStatus,
  StrategyBaseline,
  StrategyHealthLog,
  StrategyAlert,
  StrategyStateTransition,
} from "@/types/health";

const STATE_COLORS: Record<string, string> = {
  ACTIVE: "#146c5d", // Green
  WARNING: "#d97706", // Amber
  CRITICAL: "#b42318", // Red
  PAUSED: "#6b7280", // Gray
};

const STATE_LABELS: Record<string, string> = {
  ACTIVE: "AKTİF",
  WARNING: "UYARI (WARNING)",
  CRITICAL: "KRİTİK (CRITICAL)",
  PAUSED: "DURAKLATILDI",
};

const ALERT_COLORS: Record<string, string> = {
  GREEN: "bg-emerald-50 text-emerald-700 border-emerald-200",
  YELLOW: "bg-amber-50 text-amber-700 border-amber-200",
  ORANGE: "bg-orange-50 text-orange-700 border-orange-200",
  RED: "bg-rose-50 text-rose-700 border-rose-200",
};

export default function StrategyHealthPage() {
  const [token, setToken] = useState("");
  const [strategyName, setStrategyName] = useState("capital_preservation_v1");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [activeChartMetric, setActiveChartMetric] = useState<
    "sharpe" | "win_rate" | "profit_factor" | "drawdown"
  >("sharpe");

  const [healthStatus, setHealthStatus] = useState<StrategyHealthStatus | null>(null);
  const [baseline, setBaseline] = useState<StrategyBaseline | null>(null);
  const [metricsHistory, setMetricsHistory] = useState<StrategyHealthLog[]>([]);
  const [alerts, setAlerts] = useState<StrategyAlert[]>([]);
  const [transitions, setTransitions] = useState<StrategyStateTransition[]>([]);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  const refresh = useCallback(async () => {
    if (!token || !strategyName) return;
    setLoading(true);
    try {
      const [health, base, metrics, alertList, transList] = await Promise.all([
        getStrategyHealth(strategyName),
        getStrategyBaseline(strategyName),
        getHealthMetrics(strategyName),
        getStrategyAlerts(strategyName),
        getTransitions(strategyName),
      ]);

      if (health) setHealthStatus(health);
      if (base) setBaseline(base);
      setMetricsHistory(metrics);
      setAlerts(alertList);
      setTransitions(transList);
    } finally {
      setLoading(false);
    }
  }, [token, strategyName]);

  useEffect(() => {
    if (!token || !strategyName) return;
    refresh();
    intervalRef.current = setInterval(refresh, 5000); // 5s auto-refresh
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [token, strategyName, refresh]);

  async function handleRecalculate() {
    if (!token) return;
    setActionLoading(true);
    try {
      const result = await recalculateStrategyHealth(strategyName);
      if (result) {
        setHealthStatus(result);
        alert("Strateji sağlık parametreleri ve sapma değerleri geçmişe yönelik başarıyla yeniden hesaplandı!");
        await refresh();
      }
    } finally {
      setActionLoading(false);
    }
  }

  async function handlePause() {
    if (!token) return;
    setActionLoading(true);
    try {
      const success = await pauseStrategy(strategyName);
      if (success) {
        alert(`Strateji (${strategyName}) başarıyla duraklatıldı.`);
        await refresh();
      }
    } finally {
      setActionLoading(false);
    }
  }

  async function handleResume() {
    if (!token) return;
    setActionLoading(true);
    try {
      const success = await resumeStrategy(strategyName);
      if (success) {
        alert(`Strateji (${strategyName}) başarıyla yeniden aktif edildi.`);
        await refresh();
      }
    } finally {
      setActionLoading(false);
    }
  }

  // Format charts for Expected vs Actual comparison
  const chartData = metricsHistory.map((m) => {
    const time = new Date(m.created_at).toLocaleTimeString("tr-TR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

    const expectedVal = (() => {
      if (!baseline) return 0;
      switch (activeChartMetric) {
        case "sharpe":
          return Number(baseline.expected_sharpe);
        case "win_rate":
          return Number(baseline.expected_win_rate);
        case "profit_factor":
          return Number(baseline.expected_profit_factor);
        case "drawdown":
          return Number(baseline.expected_drawdown);
        default:
          return 0;
      }
    })();

    const actualVal = (() => {
      switch (activeChartMetric) {
        case "sharpe":
          return Number(m.rolling_sharpe);
        case "win_rate":
          return Number(m.rolling_win_rate);
        case "profit_factor":
          return Number(m.rolling_profit_factor);
        case "drawdown":
          return Number(m.rolling_drawdown);
        default:
          return 0;
      }
    })();

    return {
      time,
      "Gerçekleşen (Actual)": actualVal,
      "Beklenen (Expected)": expectedVal,
    };
  });

  const currentHealth = Number(healthStatus?.health_score ?? 100);
  const currentDrift = Number(healthStatus?.drift_score ?? 0);
  const currentState = healthStatus?.state ?? "ACTIVE";
  const currentFailureMode = healthStatus?.failure_mode ?? "None";
  const currentAnomaly = healthStatus?.anomaly ?? "NORMAL";

  // State Badge Component style selector
  const stateColor = STATE_COLORS[currentState] ?? "#6b7280";
  const stateLabel = STATE_LABELS[currentState] ?? currentState;

  // Failure Mode localized mapper
  const getFailureModeLabel = (mode: string) => {
    switch (mode) {
      case "Gradual Decay":
        return "Kademeli Performans Kaybı (Gradual Decay)";
      case "Sudden Collapse":
        return "Ani Strateji Çöküşü (Sudden Collapse)";
      case "Regime Mismatch":
        return "Piyasa Rejimi Uyuşmazlığı (Regime Mismatch)";
      case "Volatility Mismatch":
        return "Volatilite Uyuşmazlığı (Volatility Mismatch)";
      case "None":
      default:
        return "Arıza Tespit Edilmedi (Sağlıklı)";
    }
  };

  return (
    <main className="min-h-screen bg-[#f7f7f4]">
      {/* ─── Header ─── */}
      <header className="border-b border-[#deded8] bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold text-[#146c5d]">
              Strateji Sağlık İzleme Sistemi (Strategy Health Monitor)
            </h1>
            <p className="text-sm text-muted">
              Stratejilerin canlı performans, bozulma (decay), sapma ve anomali analizi
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Input
              className="w-48"
              placeholder="Strateji Adı"
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
            />
            <Button onClick={refresh} disabled={loading || !token}>
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} /> Yenile
            </Button>
          </div>
        </div>
        {token && (
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-6 pb-4">
            <div className="flex flex-wrap gap-2">
              <Button
                onClick={handleRecalculate}
                disabled={actionLoading}
                className="bg-transparent border border-[#deded8] text-slate-700 hover:bg-slate-100"
              >
                <RotateCcw size={15} /> Parametreleri Yeniden Hesapla (Recalculate)
              </Button>
              {currentState === "PAUSED" ? (
                <Button className="bg-[#146c5d] hover:bg-[#0f5449]" onClick={handleResume} disabled={actionLoading}>
                  <Play size={15} /> Stratejiyi Devam Ettir (Resume)
                </Button>
              ) : (
                <Button className="bg-[#b42318] hover:bg-[#8e1b13]" onClick={handlePause} disabled={actionLoading}>
                  <Pause size={15} /> Stratejiyi Duraklat (Pause)
                </Button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted">Strateji Durumu:</span>
              <span
                className="inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold text-white shadow-sm"
                style={{ backgroundColor: stateColor }}
              >
                {stateLabel}
              </span>
            </div>
          </div>
        )}
      </header>

      {/* ─── Metrics Grid ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4">
        {/* Health Score */}
        <Card className="flex flex-col justify-between">
          <div>
            <div className="mb-2 flex items-center justify-between text-sm text-muted">
              <span>Sağlık Skoru (Health Score)</span>
              <ShieldCheck size={18} className="text-[#146c5d]" />
            </div>
            <div className="text-3xl font-bold" style={{ color: currentHealth < 50 ? "#b42318" : currentHealth < 75 ? "#d97706" : "#146c5d" }}>
              {currentHealth.toFixed(1)}%
            </div>
          </div>
          <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${currentHealth}%`,
                backgroundColor: currentHealth < 50 ? "#b42318" : currentHealth < 75 ? "#d97706" : "#146c5d",
              }}
            />
          </div>
        </Card>

        {/* Drift Score */}
        <Card className="flex flex-col justify-between">
          <div>
            <div className="mb-2 flex items-center justify-between text-sm text-muted">
              <span>Sapma Skoru (Drift Score)</span>
              <TrendingUp size={18} className="text-muted" />
            </div>
            <div className="text-3xl font-bold" style={{ color: currentDrift > 0.5 ? "#b42318" : currentDrift > 0.25 ? "#d97706" : "#146c5d" }}>
              {currentDrift.toFixed(3)}
            </div>
          </div>
          <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${Math.min(currentDrift * 100, 100)}%`,
                backgroundColor: currentDrift > 0.5 ? "#b42318" : currentDrift > 0.25 ? "#d97706" : "#146c5d",
              }}
            />
          </div>
        </Card>

        {/* Failure Mode */}
        <Card className="flex flex-col justify-between">
          <div>
            <div className="mb-2 flex items-center justify-between text-sm text-muted">
              <span>Hata Teşhisi (Failure Mode)</span>
              <AlertTriangle size={18} className="text-muted" />
            </div>
            <div className={`text-base font-semibold ${currentFailureMode !== "None" ? "text-[#b42318]" : "text-[#146c5d]"}`}>
              {getFailureModeLabel(currentFailureMode)}
            </div>
          </div>
          <div className="mt-2 text-xs text-muted">
            {currentFailureMode !== "None" ? "Sağlık durumu etkilendi." : "Strateji normal davranış sergiliyor."}
          </div>
        </Card>

        {/* Anomaly Detector */}
        <Card className="flex flex-col justify-between">
          <div>
            <div className="mb-2 flex items-center justify-between text-sm text-muted">
              <span>Anomali Durumu (Anomaly Status)</span>
              <AlertCircle size={18} className="text-muted" />
            </div>
            <div className={`text-lg font-bold ${currentAnomaly === "ANOMALOUS" ? "text-[#b42318]" : "text-[#146c5d]"}`}>
              {currentAnomaly === "ANOMALOUS" ? "⚠️ ANOMALİ TESPİT EDİLDİ" : "✅ NORMAL"}
            </div>
          </div>
          <div className="mt-2 text-xs text-muted">
            {currentAnomaly === "ANOMALOUS"
              ? "Sıra dışı işlem/zarar serisi tespit edildi!"
              : "İşlem serileri istatistiksel sınırlar içinde."}
          </div>
        </Card>
      </section>

      {/* ─── Row 1: Charts & Expected vs Actual selector ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        <Card className="flex flex-col justify-between">
          <div>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
              <div>
                <h2 className="text-base font-semibold text-[#146c5d]">
                  Performans Karşılaştırma Grafiği (Expected vs Actual)
                </h2>
                <p className="text-xs text-muted">
                  Stratejinin geçmiş backtest/beklenti değeri ile canlı gerçekleşen verisinin kıyası
                </p>
              </div>
              <div className="flex rounded-md border border-[#deded8] bg-slate-100 p-0.5 text-xs">
                <button
                  className={`rounded px-2.5 py-1 font-semibold transition-all ${
                    activeChartMetric === "sharpe" ? "bg-white text-[#146c5d] shadow" : "text-muted hover:text-black"
                  }`}
                  onClick={() => setActiveChartMetric("sharpe")}
                >
                  Sharpe
                </button>
                <button
                  className={`rounded px-2.5 py-1 font-semibold transition-all ${
                    activeChartMetric === "win_rate" ? "bg-white text-[#146c5d] shadow" : "text-muted hover:text-black"
                  }`}
                  onClick={() => setActiveChartMetric("win_rate")}
                >
                  Win Rate
                </button>
                <button
                  className={`rounded px-2.5 py-1 font-semibold transition-all ${
                    activeChartMetric === "profit_factor" ? "bg-white text-[#146c5d] shadow" : "text-muted hover:text-black"
                  }`}
                  onClick={() => setActiveChartMetric("profit_factor")}
                >
                  Profit Factor
                </button>
                <button
                  className={`rounded px-2.5 py-1 font-semibold transition-all ${
                    activeChartMetric === "drawdown" ? "bg-white text-[#146c5d] shadow" : "text-muted hover:text-black"
                  }`}
                  onClick={() => setActiveChartMetric("drawdown")}
                >
                  Drawdown
                </button>
              </div>
            </div>
            <div className="h-72">
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <CartesianGrid stroke="#ecece7" />
                    <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip />
                    <Legend />
                    <Area
                      type="monotone"
                      dataKey="Gerçekleşen (Actual)"
                      stroke="#146c5d"
                      fill="#146c5d22"
                      strokeWidth={2}
                    />
                    <Area
                      type="monotone"
                      dataKey="Beklenen (Expected)"
                      stroke="#d97706"
                      fill="none"
                      strokeDasharray="4 4"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-muted">
                  Performans geçmişi veya baseline bulunmuyor.
                </div>
              )}
            </div>
          </div>
        </Card>

        {/* Baseline & Performance Summary */}
        <Card className="flex flex-col justify-between">
          <div>
            <h2 className="mb-3 text-base font-semibold text-[#146c5d]">
              Beklenti Değerleri (Baseline)
            </h2>
            <p className="mb-4 text-xs text-muted">
              Stratejinin onaylanmış tarihsel performans beklentileri
            </p>
            {baseline ? (
              <div className="space-y-3.5 text-sm">
                <div className="flex justify-between border-b border-[#deded8] pb-2">
                  <span className="text-muted">Expected Sharpe:</span>
                  <span className="font-semibold">{Number(baseline.expected_sharpe).toFixed(2)}</span>
                </div>
                <div className="flex justify-between border-b border-[#deded8] pb-2">
                  <span className="text-muted">Expected Win Rate:</span>
                  <span className="font-semibold">{(Number(baseline.expected_win_rate) * 100).toFixed(1)}%</span>
                </div>
                <div className="flex justify-between border-b border-[#deded8] pb-2">
                  <span className="text-muted">Expected Profit Factor:</span>
                  <span className="font-semibold">{Number(baseline.expected_profit_factor).toFixed(2)}</span>
                </div>
                <div className="flex justify-between border-b border-[#deded8] pb-2">
                  <span className="text-muted">Expected Max Drawdown:</span>
                  <span className="font-semibold text-[#b42318]">
                    {(Number(baseline.expected_drawdown) * 100).toFixed(2)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Expected Freq (Trades/Day):</span>
                  <span className="font-semibold">{Number(baseline.expected_trade_frequency).toFixed(1)}</span>
                </div>
              </div>
            ) : (
              <div className="py-6 text-center text-sm text-muted">
                Baseline verisi yüklenemedi veya yok.
              </div>
            )}
          </div>
          <div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-muted">
            ℹ️ Gerçekleşen performans değerleri, beklenen baseline değerlerinin altına düştüğünde sapma tetiklenir ve risk limitleri daraltılır.
          </div>
        </Card>
      </section>

      {/* ─── Row 2: Alert List & Transitions Timeline ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-10 lg:grid-cols-2">
        {/* Alert Logs */}
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-[#146c5d]">Sağlık Alarmları (Alert Logs)</h2>
            <span className="text-xs text-muted">Son 100 kayıt</span>
          </div>
          <div className="max-h-[300px] overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-[#deded8] text-muted">
                <tr>
                  <th className="py-2">Zaman</th>
                  <th>Seviye</th>
                  <th>Mesaj</th>
                  <th>Alınan Aksiyon</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id} className="border-b border-[#deded8] hover:bg-slate-50">
                    <td className="py-2.5 text-muted">
                      {new Date(a.created_at).toLocaleString("tr-TR")}
                    </td>
                    <td>
                      <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold border ${ALERT_COLORS[a.alert_level] ?? "bg-slate-50 text-slate-700"}`}>
                        {a.alert_level}
                      </span>
                    </td>
                    <td className="max-w-[200px] truncate pr-2 font-medium text-slate-800" title={a.message}>
                      {a.message}
                    </td>
                    <td className="text-slate-600 font-semibold">{a.action_taken}</td>
                  </tr>
                ))}
                {alerts.length === 0 && (
                  <tr>
                    <td className="py-6 text-center text-muted" colSpan={4}>
                      Kayıtlı alarm bulunmuyor.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Transition Timeline */}
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-[#146c5d]">Strateji Durum Geçişleri</h2>
            <span className="text-xs text-muted">Durum Değişikliği Tarihçesi</span>
          </div>
          <div className="max-h-[300px] overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-[#deded8] text-muted">
                <tr>
                  <th className="py-2">Zaman</th>
                  <th>Eski Durum</th>
                  <th className="px-2" />
                  <th>Yeni Durum</th>
                  <th>Neden / Tetikleyici</th>
                </tr>
              </thead>
              <tbody>
                {transitions.map((t) => (
                  <tr key={t.id} className="border-b border-[#deded8] hover:bg-slate-50">
                    <td className="py-2.5 text-muted">
                      {new Date(t.created_at).toLocaleString("tr-TR")}
                    </td>
                    <td>
                      <span
                        className="inline-block rounded-full px-2 py-0.5 text-[10px] font-bold text-white"
                        style={{ backgroundColor: STATE_COLORS[t.old_state] ?? "#6b7280" }}
                      >
                        {STATE_LABELS[t.old_state] ?? t.old_state}
                      </span>
                    </td>
                    <td className="px-1 text-muted">
                      <ArrowRightLeft size={12} className="inline" />
                    </td>
                    <td>
                      <span
                        className="inline-block rounded-full px-2 py-0.5 text-[10px] font-bold text-white"
                        style={{ backgroundColor: STATE_COLORS[t.new_state] ?? "#6b7280" }}
                      >
                        {STATE_LABELS[t.new_state] ?? t.new_state}
                      </span>
                    </td>
                    <td className="max-w-[200px] truncate text-slate-700 font-medium" title={t.trigger_reason}>
                      {t.trigger_reason}
                    </td>
                  </tr>
                ))}
                {transitions.length === 0 && (
                  <tr>
                    <td className="py-6 text-center text-muted" colSpan={5}>
                      Durum değişikliği kaydı bulunmuyor.
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
