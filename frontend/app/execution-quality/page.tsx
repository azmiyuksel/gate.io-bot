"use client";

import {
  Activity,
  AlertCircle,
  AlertTriangle,
  Clock,
  HelpCircle,
  Info,
  Landmark,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useCallback, useEffect, useRef, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LastUpdated } from "@/components/ui/last-updated";
import { Metric } from "@/components/ui/metric";
import { useToast } from "@/components/ui/toast";
import { getAccessToken } from "@/lib/auth-api";
import { money } from "@/lib/utils";
import {
  getStrategyExecutionStatus,
  getSlippageLogs,
  getLatencyLogs,
  getExecutionReport,
  recalculateExecutionQuality,
} from "@/lib/execution-quality-api";
import type {
  ExecutionQualityStatus,
  ExecutionSlippageLog,
  ExecutionLatencyLog,
  ExecutionReport,
} from "@/types/execution-quality";

const CATEGORY_COLORS: Record<string, string> = {
  Excellent: "#146c5d",     // Emerald Green
  Good: "#0f766e",          // Teal
  Acceptable: "#d97706",    // Amber
  Poor: "#b42318",          // Red
};

const CATEGORY_BG_CLASSES: Record<string, string> = {
  Excellent: "bg-emerald-700",
  Good: "bg-teal-700",
  Acceptable: "bg-amber-600",
  Poor: "bg-red-700",
};

const CATEGORY_TEXT_CLASSES: Record<string, string> = {
  Excellent: "text-emerald-700",
  Good: "text-teal-700",
  Acceptable: "text-amber-600",
  Poor: "text-red-700",
};

const CATEGORY_LABELS: Record<string, string> = {
  Excellent: "Mükemmel (Excellent)",
  Good: "İyi (Good)",
  Acceptable: "Kabul Edilebilir",
  Poor: "Zayıf (Poor Execution)",
};

const ANOMALY_COLORS: Record<string, string> = {
  NORMAL: "text-[#146c5d]",
  ANOMALOUS: "text-[#b42318] font-bold animate-pulse",
};

const RECOMMENDATION_SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "bg-rose-50 text-rose-700 border-rose-200",
  HIGH: "bg-orange-50 text-orange-700 border-orange-200",
  MEDIUM: "bg-amber-50 text-amber-700 border-amber-200",
  INFO: "bg-blue-50 text-blue-700 border-blue-200",
};

export default function ExecutionQualityPage() {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [strategyName, setStrategyName] = useState("capital_preservation_v1");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [status, setStatus] = useState<ExecutionQualityStatus | null>(null);
  const [slippageLogs, setSlippageLogs] = useState<ExecutionSlippageLog[]>([]);
  const [latencyLogs, setLatencyLogs] = useState<ExecutionLatencyLog[]>([]);
  const [report, setReport] = useState<ExecutionReport | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  const refresh = useCallback(async () => {
    if (!token || !strategyName) return;
    setLoading(true);
    try {
      const [statusData, slipData, latData, reportData] = await Promise.all([
        getStrategyExecutionStatus(strategyName).catch(() => null),
        getSlippageLogs(strategyName, 50).catch(() => []),
        getLatencyLogs(strategyName, 50).catch(() => []),
        getExecutionReport(strategyName, 30).catch(() => null),
      ]);

      if (statusData) setStatus(statusData);
      setSlippageLogs(slipData);
      setLatencyLogs(latData);
      if (reportData) setReport(reportData);
      setLastUpdated(new Date());
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
      const result = await recalculateExecutionQuality(strategyName);
      if (result) {
        setStatus(result);
        toast("Emir icra kalitesi metrikleri veritabanındaki tüm işlemler taranarak yeniden hesaplandı!", "success");
        await refresh();
      }
    } finally {
      setActionLoading(false);
    }
  }

  // Format slippage chart data (chronological)
  const slippageChartData = [...slippageLogs]
    .reverse()
    .map((log) => ({
      time: new Date(log.created_at).toLocaleTimeString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
      "Slippage (%)": Math.abs(Number(log.slippage_pct)) * 100,
    }));

  // Format latency stack chart data
  const latencyChartData = [...latencyLogs]
    .reverse()
    .map((log) => ({
      time: new Date(log.created_at).toLocaleTimeString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
      "Sinyal -> Onay (ms)": log.signal_to_submit_ms + log.submit_to_ack_ms,
      "Eşleşme -> Dolum (ms)": log.ack_to_fill_ms,
      "Toplam Gecikme (ms)": log.total_execution_delay_ms,
    }));

  const currentScore = Number(status?.execution_quality_score ?? 100);
  const avgSlippage = Number(status?.slippage_avg ?? 0);
  const avgLatency = Number(status?.latency_total_execution_ms ?? 0);
  const fillCompletion = Number(status?.fill_completion_rate ?? 1.0);
  const partialRatio = Number(status?.partial_fill_ratio ?? 0.0);
  const category = status?.quality_category ?? "Excellent";
  const anomaly = status?.anomaly_status ?? "NORMAL";
  const anomalyReason = status?.anomaly_reason ?? "normal";

  const colorCode = CATEGORY_COLORS[category] ?? "#6b7280";
  const categoryLabel = CATEGORY_LABELS[category] ?? category;

  // Retrieve distribution for slippage category chart
  const slippageDist = report?.report_data?.slippage_distribution ?? {
    good: 0,
    normal: 0,
    bad: 0,
    critical: 0,
  };
  
  const distChartData = [
    { name: "Mükemmel (<%0.05)", adet: slippageDist.good, fill: "#146c5d" },
    { name: "Normal (%0.05-%0.2)", adet: slippageDist.normal, fill: "#0f766e" },
    { name: "Kötü (%0.2-%0.5)", adet: slippageDist.bad, fill: "#d97706" },
    { name: "Kritik (>%0.5)", adet: slippageDist.critical, fill: "#b42318" },
  ];

  return (
    <main className="min-h-screen bg-[#f7f7f4]">
      {/* ─── Header ─── */}
      <header className="border-b border-[#deded8] bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <Breadcrumb items={[{ label: "İcra Kalitesi" }]} />
            <h1 className="text-xl font-semibold text-[#146c5d]">
              Emir İcra Kalitesi Analiz Sistemi (Execution Quality Engine)
            </h1>
            <p className="text-sm text-muted">
              Gerçekleşen emirlerin slippage, latency, fill kalitesi ve ideal fiyat sapmalarının izlenmesi
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
            <div className="flex gap-2">
              <Button
                onClick={handleRecalculate}
                disabled={actionLoading}
                className="bg-transparent border border-[#deded8] text-slate-700 hover:bg-slate-100"
              >
                <RotateCcw size={15} /> Metrikleri Yeniden Hesapla (Recalculate)
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <LastUpdated time={lastUpdated} />
              <span className="text-sm text-muted">İcra Derecesi:</span>
              <span
                className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold text-white shadow-sm ${CATEGORY_BG_CLASSES[category] ?? "bg-slate-500"}`}
              >
                {categoryLabel}
              </span>
            </div>
          </div>
        )}
      </header>

      {/* ─── Metrics Grid ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4">
        {/* Quality Score */}
        <Card className="flex flex-col justify-between">
          <div>
            <div className="mb-2 flex items-center justify-between text-sm text-muted">
              <span>İcra Kalite Skoru (Overall Score)</span>
              <ShieldCheck size={18} className="text-[#146c5d]" />
            </div>
            <div className={`text-3xl font-bold ${CATEGORY_TEXT_CLASSES[category] ?? "text-slate-600"}`}>
              {currentScore.toFixed(1)} / 100
            </div>
          </div>
          <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${currentScore}%`,
                backgroundColor: colorCode,
              }}
            />
          </div>
        </Card>

        {/* Avg Slippage */}
        <Card className="flex flex-col justify-between">
          <div>
            <div className="mb-2 flex items-center justify-between text-sm text-muted">
              <span>Ortalama Kayma (Avg Slippage)</span>
              <TrendingDown size={18} className="text-muted" />
            </div>
            <div className="text-3xl font-bold text-slate-800">
              {avgSlippage >= 0 ? "+" : ""}{(avgSlippage * 100).toFixed(3)}%
            </div>
          </div>
          <div className="mt-2 text-xs text-muted">
            {Math.abs(avgSlippage) <= 0.0005
              ? "Mükemmel icra fiyat doğruluğu."
              : Math.abs(avgSlippage) <= 0.0020
              ? "Normal sınırlar içinde."
              : "Kritik kayma uyarısı!"}
          </div>
        </Card>

        {/* Avg Latency */}
        <Card className="flex flex-col justify-between">
          <div>
            <div className="mb-2 flex items-center justify-between text-sm text-muted">
              <span>Ortalama Latency (Gecikme)</span>
              <Clock size={18} className="text-muted" />
            </div>
            <div className="text-3xl font-bold text-slate-800">
              {avgLatency.toFixed(1)} ms
            </div>
          </div>
          <div className="mt-2 text-xs text-muted">
            Toplam gecikme süresi (Sinyal → Dolum)
          </div>
        </Card>

        {/* Anomaly / Execution Health */}
        <Card className="flex flex-col justify-between">
          <div>
            <div className="mb-2 flex items-center justify-between text-sm text-muted">
              <span>İcra Anomali Kontrolü</span>
              <AlertCircle size={18} className="text-muted" />
            </div>
            <div className={`text-lg font-bold ${ANOMALY_COLORS[anomaly]}`}>
              {anomaly === "ANOMALOUS" ? "⚠️ ANOMALİ ALARMI" : "✅ NORMAL"}
            </div>
          </div>
          <div className="mt-2 text-xs text-muted truncate" title={anomalyReason}>
            {anomaly === "ANOMALOUS" ? anomalyReason : "Herhangi bir icra anomali tetiklenmedi."}
          </div>
        </Card>
      </section>

      {/* ─── Row 1: Charts (Slippage & Latency) ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 sm:grid-cols-2 lg:grid-cols-2">
        {/* Slippage Area Chart */}
        <Card>
          <div className="mb-4">
            <h2 className="text-base font-semibold text-[#146c5d]">Fiyat Kayması Trendi (Slippage over Time)</h2>
            <p className="text-xs text-muted">İşlemlerde gerçekleşen mutlak fiyat sapması yüzdesi</p>
          </div>
          <div className="h-72">
            {slippageChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={slippageChartData}>
                  <CartesianGrid stroke="#ecece7" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} label={{ value: "Slippage %", angle: -90, position: "insideLeft", style: { fontSize: 10 } }} />
                  <Tooltip formatter={(v: number) => `${v.toFixed(3)}%`} />
                  <Area type="monotone" dataKey="Slippage (%)" stroke="#146c5d" fill="#146c5d22" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">
                Kayıtlı fiyat kayması verisi bulunmuyor.
              </div>
            )}
          </div>
        </Card>

        {/* Latency Stacked Bar Chart */}
        <Card>
          <div className="mb-4">
            <h2 className="text-base font-semibold text-[#146c5d]">Gecikme Dağılım Kırılımı (Latency Breakdown)</h2>
            <p className="text-xs text-muted">İşlem basamaklarının milisaniye bazında gecikme analizi</p>
          </div>
          <div className="h-72">
            {latencyChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={latencyChartData}>
                  <CartesianGrid stroke="#ecece7" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 10 }} />
                  <Bar dataKey="Sinyal -> Onay (ms)" stackId="a" fill="#0f766e" />
                  <Bar dataKey="Eşleşme -> Dolum (ms)" stackId="a" fill="#d97706" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">
                Gecikme geçmişi kaydı bulunmuyor.
              </div>
            )}
          </div>
        </Card>
      </section>

      {/* ─── Row 2: Fill statistics & Strategy execution impact ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 sm:grid-cols-2 lg:grid-cols-[2fr_1fr]">
        {/* Fill statistics / report */}
        <Card>
          <h2 className="mb-4 text-base font-semibold text-[#146c5d]">
            30 Günlük İcra Performans Raporu ve Dolum Analizi
          </h2>
          {report ? (
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="space-y-3.5 text-sm">
                <div className="flex justify-between border-b border-[#deded8] pb-2">
                  <span className="text-muted">Toplam Gönderilen Emir:</span>
                  <span className="font-semibold">{report.total_orders}</span>
                </div>
                <div className="flex justify-between border-b border-[#deded8] pb-2">
                  <span className="text-muted">Toplam Gerçekleşen Dolum:</span>
                  <span className="font-semibold">{report.total_fills}</span>
                </div>
                <div className="flex justify-between border-b border-[#deded8] pb-2">
                  <span className="text-muted">Ortalama Gecikme (Turnaround):</span>
                  <span className="font-semibold">{Number(report.average_latency_ms).toFixed(1)} ms</span>
                </div>
                <div className="flex justify-between border-b border-[#deded8] pb-2">
                  <span className="text-muted">Ortalama Fiyat Kayması:</span>
                  <span className="font-semibold">%{ (Number(report.average_slippage_pct) * 100).toFixed(3) }</span>
                </div>
                <div className="flex justify-between border-b border-[#deded8] pb-2">
                  <span className="text-muted">Kısmi Dolum Oranı (Partial Fill):</span>
                  <span className="font-semibold text-amber-600">%{ (partialRatio * 100).toFixed(1) }</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Emir Tamamlanma Oranı (Fill rate):</span>
                  <span className="font-semibold text-[#146c5d]">%{ (fillCompletion * 100).toFixed(1) }</span>
                </div>
              </div>

              {/* Graphical distribution of slippage category */}
              <div>
                <h3 className="mb-2 text-xs font-semibold text-muted">Slippage Kategorileri Dağılımı</h3>
                <div className="h-44">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={distChartData} layout="vertical">
                      <XAxis type="number" tick={{ fontSize: 9 }} />
                      <YAxis dataKey="name" type="category" tick={{ fontSize: 9 }} width={120} />
                      <Tooltip />
                      <Bar dataKey="adet" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          ) : (
            <div className="py-12 text-center text-sm text-muted">
              İcra kalite raporu yüklenemedi.
            </div>
          )}
        </Card>

        {/* Strategy execution impact */}
        <Card className="flex flex-col justify-between">
          <div>
            <h2 className="mb-3 text-base font-semibold text-[#146c5d]">Strateji Performans Etkisi</h2>
            <p className="mb-4 text-xs text-muted">
              Yetersiz execution kalitesinin finansal performansa yansıması
            </p>
            {report ? (
              <div className="space-y-4 text-sm">
                <div className="rounded-lg bg-red-50 p-3 border border-red-100 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <TrendingDown className="text-[#b42318]" size={18} />
                    <span className="text-xs text-red-900 font-semibold">Slippage Maliyeti (USD)</span>
                  </div>
                  <span className="text-base font-bold text-[#b42318]">${money(report.slippage_cost_usd)}</span>
                </div>
                <div className="rounded-lg bg-amber-50 p-3 border border-amber-100 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Activity className="text-amber-700" size={18} />
                    <span className="text-xs text-amber-900 font-semibold">Sharpe Oranı Kaybı</span>
                  </div>
                  <span className="text-base font-bold text-amber-700">-{Number(report.sharpe_decay).toFixed(2)}</span>
                </div>
              </div>
            ) : (
              <div className="py-6 text-center text-sm text-muted">Veri bulunmuyor.</div>
            )}
          </div>
          <div className="mt-4 rounded bg-slate-50 p-3 text-xs text-muted border border-slate-100">
            ℹ️ Fiyat kayması maliyeti, gerçekleşen işlemler ile理想fiyat arasındaki farkın toplam işlem hacmiyle çarpılmasıyla hesaplanır.
          </div>
        </Card>
      </section>

      {/* ─── Row 3: Optimizer Recommendations & Spread/Volatility Correlation ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-10 sm:grid-cols-2 lg:grid-cols-2">
        {/* Adaptive execution recommendations */}
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold text-[#146c5d]">Adaptif İcra Önerileri (Optimizer)</h2>
            <span className="text-xs text-muted">Canlı Akıllı Yönlendirme</span>
          </div>
          <div className="space-y-3 max-h-[300px] overflow-y-auto pr-1">
            {report?.report_data?.recommendations?.map((rec, i) => (
              <div
                key={i}
                className={`flex items-start gap-3 rounded-lg border p-3.5 text-xs ${
                  RECOMMENDATION_SEVERITY_COLORS[rec.severity] ?? "bg-slate-50 border-slate-200 text-slate-700"
                }`}
              >
                <Info size={16} className="mt-0.5 shrink-0" />
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold">{rec.type}</span>
                    <span className="rounded px-1.5 py-0.2 text-xs font-extrabold border bg-white uppercase">
                      {rec.severity}
                    </span>
                  </div>
                  <p className="text-slate-800 font-medium leading-relaxed">{rec.message}</p>
                  <p className="text-slate-600 font-bold mt-1">Önerilen Aksiyon: <span className="underline">{rec.action}</span></p>
                </div>
              </div>
            ))}
            {(!report?.report_data?.recommendations || report.report_data.recommendations.length === 0) && (
              <div className="py-6 text-center text-sm text-muted">
                Tavsiye oluşturmak için yeterli veri yok.
              </div>
            )}
          </div>
        </Card>

        {/* Market Condition Correlation Table */}
        <Card>
          <div className="mb-4">
            <h2 className="text-base font-semibold text-[#146c5d]">Piyasa Koşulları Korelasyon Analizi</h2>
            <p className="text-xs text-muted">Execution kalitesi ile piyasa parametrelerinin ilişkisi</p>
          </div>
          <div className="overflow-x-auto">
            <table role="table" className="w-full text-left text-xs">
              <thead className="border-b border-[#deded8] text-muted">
                <tr>
                  <th scope="col" className="py-2">Piyasa Göstergesi</th>
                  <th scope="col">Korelasyon Skoru</th>
                  <th scope="col">Execution Etkisi</th>
                  <th scope="col">Durum</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="py-6 text-center text-muted" colSpan={4}>
                    Korelasyon verisi henüz mevcut değil. Yeterli piyasa verisi toplandığında otomatik olarak hesaplanacak.
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      </section>
    </main>
  );
}
