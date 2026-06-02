"use client";

import { Play } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { authFetch } from "@/lib/auth-api";

export function BacktestCreate() {
  const router = useRouter();
  const [symbol, setSymbol] = useState("BTC_USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [startAt, setStartAt] = useState("2024-01-01T00:00:00Z");
  const [endAt, setEndAt] = useState("2024-12-31T23:59:59Z");
  const [initialCash, setInitialCash] = useState("10000");
  const [dataSource, setDataSource] = useState("cache");
  const [parameters, setParameters] = useState('{"ema_trend":200,"rsi_threshold":35,"atr_multiplier":1.5}');
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    setError("");

    let parsedParameters: unknown;
    try {
      parsedParameters = JSON.parse(parameters);
    } catch {
      setError("Parametreler geçerli JSON değil.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await authFetch(`/backtests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          timeframe,
          start_at: startAt,
          end_at: endAt,
          initial_cash: initialCash,
          data_source: dataSource,
          parameters: parsedParameters,
        }),
      });
      if (response.ok) {
        const result = await response.json();
        router.push(`/backtests/results/${result.id}`);
        return;
      }
      if (response.status === 401) {
        setError("Oturum gerekli. Lütfen panelden giriş yapın.");
      } else {
        const detail = await response.json().catch(() => null);
        setError(detail?.detail ? `Hata: ${detail.detail}` : "Backtest başlatılamadı.");
      }
    } catch {
      setError("Sunucuya ulaşılamadı.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto max-w-4xl px-6 py-4">
          <h1 className="text-xl font-semibold">Yeni Backtest</h1>
          <p className="text-sm text-muted">Cache, CSV veya Gate.io verisiyle strateji simülasyonu oluştur</p>
        </div>
      </header>
      <section className="mx-auto max-w-4xl px-6 py-6">
        <Card className="grid gap-4">
          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">{error}</div>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Sembol"><Input value={symbol} onChange={(event) => setSymbol(event.target.value)} /></Field>
            <Field label="Timeframe"><Input value={timeframe} onChange={(event) => setTimeframe(event.target.value)} /></Field>
            <Field label="Başlangıç"><Input value={startAt} onChange={(event) => setStartAt(event.target.value)} /></Field>
            <Field label="Bitiş"><Input value={endAt} onChange={(event) => setEndAt(event.target.value)} /></Field>
            <Field label="İlk sermaye"><Input value={initialCash} onChange={(event) => setInitialCash(event.target.value)} /></Field>
            <Field label="Veri kaynağı"><Input value={dataSource} onChange={(event) => setDataSource(event.target.value)} /></Field>
          </div>
          <label className="block text-sm">
            <span className="mb-1 block text-muted">Parametreler JSON</span>
            <textarea className="min-h-28 w-full rounded-md border border-border p-3 text-sm outline-none focus:ring-2 focus:ring-primary/30" value={parameters} onChange={(event) => setParameters(event.target.value)} />
          </label>
          <Button onClick={submit} disabled={submitting}><Play size={16} /> {submitting ? "Çalışıyor..." : "Backtest Başlat"}</Button>
        </Card>
      </section>
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-muted">{label}</span>
      {children}
    </label>
  );
}
