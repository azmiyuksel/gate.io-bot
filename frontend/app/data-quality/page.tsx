"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  Gauge,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  XCircle,
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
import { useCallback, useEffect, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LastUpdated } from "@/components/ui/last-updated";
import { Metric } from "@/components/ui/metric";
import { PageSkeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { getAccessToken } from "@/lib/auth-api";
import { num } from "@/lib/utils";
import {
  getDataQualityAnomalies,
  getDataQualityHealthLogs,
  getDataQualityStatus,
  revalidateDataQuality,
} from "@/lib/data-quality-api";
import type {
  DataQualityStatus,
  MarketDataAnomaly,
  MarketDataHealthLog,
} from "@/types/data-quality";

const CATEGORY_COLORS: Record<string, string> = {
  EXCELLENT: "#146c5d",
  GOOD: "#0f766e",
  RISKY: "#d97706",
  UNRELIABLE: "#b42318",
};

const TRADE_STATUS_META: Record<string, { label: string; color: string; Icon: typeof ShieldCheck }> = {
  CLEAN: { label: "Temiz — Normal İşlem", color: "#146c5d", Icon: ShieldCheck },
  DEGRADED: { label: "Bozulmuş — Risk Azaltıldı", color: "#d97706", Icon: ShieldAlert },
  INVALID: { label: "Geçersiz — İşlem Durduruldu", color: "#b42318", Icon: XCircle },
};

const SEVERITY_COLORS: Record<string, string> = {
  INFO: "#0f766e",
  WARNING: "#d97706",
  CRITICAL: "#b42318",
};

export default function DataQualityPage() {
  const [token, setToken] = useState("");
  const [symbol, setSymbol] = useState("BTC_USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const [status, setStatus] = useState<DataQualityStatus | null>(null);
  const [anomalies, setAnomalies] = useState<MarketDataAnomaly[]>([]);
  const [healthLogs, setHealthLogs] = useState<MarketDataHealthLog[]>([]);
  const [message, setMessage] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const { toast } = useToast();

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  const refresh = useCallback(async () => {
    if (!token || !symbol) return;
    setLoading(true);
    try {
      const [s, a, h] = await Promise.all([
        getDataQualityStatus(symbol, timeframe),
        getDataQualityAnomalies(symbol, timeframe, 100),
        getDataQualityHealthLogs(symbol, timeframe, 200),
      ]);
      setStatus(s);
      setAnomalies(a);
      setHealthLogs(h);
      setLastUpdated(new Date());
    } finally {
      setLoading(false);
    }
  }, [token, symbol, timeframe]);

  useEffect(() => {
    if (!token || !symbol) return;
    refresh().catch(() => {});
    const id = setInterval(refresh, 30000);
    return () => clearInterval(id);
  }, [token, symbol, refresh]);

  const onRevalidate = useCallback(async () => {
    if (!token) return;
    setActionLoading(true);
    setMessage("");
    try {
      const result = await revalidateDataQuality(symbol, timeframe, 240);
      if (result) {
        setMessage(
          `Yeniden doğrulandı: ${result.clean_emitted}/${result.total} temiz, ` +
            `${result.anomalies} anomali, skor ${num(result.health_score).toFixed(1)} (${result.trade_status})`
        );
        toast("Yeniden doğrulama tamamlandı", "success");
        await refresh();
      } else {
        setMessage("Yeniden doğrulama başarısız (yetki/sembol kontrol edin).");
        toast("Yeniden doğrulama başarısız", "error");
      }
    } finally {
      setActionLoading(false);
    }
  }, [token, symbol, timeframe, refresh, toast]);

  const score = num(status?.health_score);
  const category = status?.category ?? "—";
  const tradeStatus = status?.trade_status ?? "CLEAN";
  const statusMeta = TRADE_STATUS_META[tradeStatus] ?? TRADE_STATUS_META.CLEAN;

  const healthSeries = healthLogs.map((h) => ({
    time: new Date(h.created_at).toLocaleString("tr-TR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }),
    score: num(h.health_score),
    missing: h.missing_candles,
    anomalies: h.anomalies_found,
  }));

  const breakdown = status
    ? [
        { name: "Tutarlılık", value: num(status.consistency_score) },
        { name: "Bütünlük", value: num(status.completeness_score) },
        { name: "Anomali (ters)", value: num(status.anomaly_inverse_score) },
        { name: "Gecikme", value: num(status.latency_score) },
      ]
    : [];

  const anomalyCounts = anomalies.reduce<Record<string, number>>((acc, a) => {
    acc[a.anomaly_type] = (acc[a.anomaly_type] ?? 0) + 1;
    return acc;
  }, {});
  const anomalyBars = Object.entries(anomalyCounts).map(([name, value]) => ({ name, value }));

  return (
    <main className="mx-auto max-w-7xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Database className="h-7 w-7 text-teal-700" />
          <div>
            <Breadcrumb items={[{ label: "Veri Kalitesi" }]} />
            <h1 className="text-2xl font-semibold">Piyasa Veri Kalite Kontrolü</h1>
            <p className="text-sm text-neutral-500">
              Gelen verinin doğruluğu, tutarlılığı ve güvenilirliği
            </p>
          </div>
          <LastUpdated time={lastUpdated} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input className="w-36" placeholder="Sembol" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
          <Input className="w-20" placeholder="TF" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} />
          <Button onClick={refresh} disabled={loading}>
            <RefreshCw className={`mr-1 h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Yenile
          </Button>
          <Button onClick={onRevalidate} disabled={actionLoading}>
            <Activity className="mr-1 h-4 w-4" /> Yeniden Doğrula
          </Button>
        </div>
      </header>

      {message && (
        <div className="rounded-md bg-teal-50 px-4 py-2 text-sm text-teal-800">{message}</div>
      )}

      {loading ? (
        <PageSkeleton />
      ) : !status ? (
        <Card className="p-8 text-center text-neutral-500">
          Token ve sembol girip "Yenile" deyin. Henüz veri kalite kaydı yoksa "Yeniden Doğrula" ile
          oluşturabilirsiniz.
        </Card>
      ) : null}

      {status && (
        <>
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
            <Card className="p-5">
              <div className="flex items-center gap-2 text-sm text-neutral-500">
                <Gauge className="h-4 w-4" /> Veri Sağlık Skoru
              </div>
              <div className="mt-2 text-3xl font-bold" style={{ color: CATEGORY_COLORS[category] ?? "#111" }}>
                {score.toFixed(1)}
              </div>
              <div className="text-sm font-medium" style={{ color: CATEGORY_COLORS[category] ?? "#111" }}>
                {category}
              </div>
            </Card>

            <Card className="p-5">
              <div className="flex items-center gap-2 text-sm text-neutral-500">
                <statusMeta.Icon className="h-4 w-4" /> İşlem Durumu
              </div>
              <div className="mt-3 text-lg font-semibold" style={{ color: statusMeta.color }}>
                {statusMeta.label}
              </div>
            </Card>

            <Card className="p-5">
              <div className="flex items-center gap-2 text-sm text-neutral-500">
                <AlertTriangle className="h-4 w-4" /> Anomaliler
              </div>
              <div className="mt-2 text-3xl font-bold text-amber-600">{status.anomalies_found}</div>
              <div className="text-sm text-neutral-500">{status.candles_evaluated} mum değerlendirildi</div>
            </Card>

            <Card className="p-5">
              <div className="flex items-center gap-2 text-sm text-neutral-500">
                <CheckCircle2 className="h-4 w-4" /> Eksik Mum / Gecikme
              </div>
              <div className="mt-2 text-3xl font-bold">{status.missing_candles}</div>
              <div className="text-sm text-neutral-500">
                feed gecikmesi {num(status.feed_latency_ms).toFixed(0)} ms
              </div>
            </Card>
          </section>

          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-2">
            <Card className="p-5">
              <h2 className="mb-3 text-sm font-semibold text-neutral-700">Skor Bileşenleri</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={breakdown}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="name" fontSize={12} />
                  <YAxis domain={[0, 100]} fontSize={12} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#0f766e" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card className="p-5">
              <h2 className="mb-3 text-sm font-semibold text-neutral-700">Sağlık Skoru Zaman Çizelgesi</h2>
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={healthSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="time" fontSize={10} minTickGap={32} />
                  <YAxis domain={[0, 100]} fontSize={12} />
                  <Tooltip />
                  <Area type="monotone" dataKey="score" stroke="#0f766e" fill="#0f766e22" />
                </AreaChart>
              </ResponsiveContainer>
            </Card>

            <Card className="p-5">
              <h2 className="mb-3 text-sm font-semibold text-neutral-700">Eksik Veri & Anomali Trendi</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={healthSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis dataKey="time" fontSize={10} minTickGap={32} />
                  <YAxis fontSize={12} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="missing" name="Eksik mum" fill="#b42318" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="anomalies" name="Anomali" fill="#d97706" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>

            <Card className="p-5">
              <h2 className="mb-3 text-sm font-semibold text-neutral-700">Anomali Türü Dağılımı</h2>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={anomalyBars} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                  <XAxis type="number" fontSize={12} />
                  <YAxis type="category" dataKey="name" width={150} fontSize={10} />
                  <Tooltip />
                  <Bar dataKey="value" fill="#0f766e" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </section>

          <Card className="p-5">
            <h2 className="mb-3 text-sm font-semibold text-neutral-700">Son Anomaliler</h2>
            <div className="overflow-x-auto">
              <table role="table" className="w-full text-left text-sm">
                <thead className="text-neutral-500">
                  <tr className="border-b">
                    <th scope="col" className="py-2 pr-4">Zaman</th>
                    <th scope="col" className="py-2 pr-4">Tür</th>
                    <th scope="col" className="py-2 pr-4">Önem</th>
                    <th scope="col" className="py-2 pr-4">Yöntem</th>
                    <th scope="col" className="py-2 pr-4">Onarım</th>
                    <th scope="col" className="py-2">Detay</th>
                  </tr>
                </thead>
                <tbody>
                  {anomalies.slice(0, 50).map((a) => (
                    <tr key={a.id} className="border-b last:border-0">
                      <td className="py-2 pr-4 whitespace-nowrap">
                        {new Date(a.timestamp).toLocaleString("tr-TR")}
                      </td>
                      <td className="py-2 pr-4 font-medium">{a.anomaly_type}</td>
                      <td className="py-2 pr-4">
                        <span
                          className="rounded px-2 py-0.5 text-xs font-semibold text-white"
                          style={{ background: SEVERITY_COLORS[a.severity] ?? "#666" }}
                        >
                          {a.severity}
                        </span>
                      </td>
                      <td className="py-2 pr-4 text-neutral-500">{a.detection_method}</td>
                      <td className="py-2 pr-4 text-neutral-500">{a.repair_action}</td>
                      <td className="py-2 text-neutral-600">{a.detail}</td>
                    </tr>
                  ))}
                  {anomalies.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-6 text-center text-neutral-400">
                        Anomali kaydı yok — veri temiz görünüyor.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      )}
    </main>
  );
}
