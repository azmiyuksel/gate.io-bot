"use client";

import { Play } from "lucide-react";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { useToast } from "@/components/ui/toast";
import { authFetch } from "@/lib/auth-api";

export function BacktestCreate() {
  const router = useRouter();
  const { toast } = useToast();
  const [symbol, setSymbol] = useState("BTC_USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [startAt, setStartAt] = useState("2024-01-01T00:00:00Z");
  const [endAt, setEndAt] = useState("2024-12-31T23:59:59Z");
  const [initialCash, setInitialCash] = useState("10000");
  const [dataSource, setDataSource] = useState("cache");
  const [parameters, setParameters] = useState('{"ema_trend":200,"rsi_threshold":35,"atr_multiplier":1.5}');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  function validate(): boolean {
    const e: Record<string, string> = {};
    if (!symbol.trim()) e.symbol = "Sembol zorunludur";
    if (!timeframe.trim()) e.timeframe = "Timeframe zorunludur";
    if (!startAt.trim()) e.startAt = "Başlangıç tarihi zorunludur";
    if (!endAt.trim()) e.endAt = "Bitiş tarihi zorunludur";
    if (!initialCash.trim() || isNaN(Number(initialCash)) || Number(initialCash) <= 0)
      e.initialCash = "Geçerli bir sermaye girin";
    if (!dataSource.trim()) e.dataSource = "Veri kaynağı zorunludur";
    try {
      JSON.parse(parameters);
    } catch {
      e.parameters = "Parametreler geçerli JSON değil";
    }
    setErrors(e);
    return Object.keys(e).length === 0;
  }

  async function submit() {
    if (!validate()) return;

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
          parameters: JSON.parse(parameters),
        }),
      });
      if (response.ok) {
        const result = await response.json();
        toast("Backtest başlatıldı", "success");
        router.push(`/backtests/results/${result.id}`);
        return;
      }
      if (response.status === 401) {
        setErrors({ submit: "Oturum gerekli. Lütfen panelden giriş yapın." });
      } else {
        const detail = await response.json().catch(() => null);
        setErrors({ submit: detail?.detail ? `Hata: ${detail.detail}` : "Backtest başlatılamadı." });
      }
    } catch {
      setErrors({ submit: "Sunucuya ulaşılamadı." });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto max-w-4xl px-6 py-4">
          <Breadcrumb items={[{ label: "Backtest", href: "/backtests" }, { label: "Yeni Backtest" }]} />
          <h1 className="mt-2 text-xl font-semibold">Yeni Backtest</h1>
          <p className="text-sm text-muted">Cache, CSV veya Gate.io verisiyle strateji simülasyonu oluştur</p>
        </div>
      </header>
      <section className="mx-auto max-w-4xl px-6 py-6">
        <Card className="grid gap-4">
          {errors.submit && (
            <div className="rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700" role="alert">
              {errors.submit}
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Sembol" error={errors.symbol}>
              <Input value={symbol} onChange={(event) => setSymbol(event.target.value)} aria-required="true" />
            </Field>
            <Field label="Timeframe" error={errors.timeframe}>
              <Input value={timeframe} onChange={(event) => setTimeframe(event.target.value)} aria-required="true" />
            </Field>
            <Field label="Başlangıç" error={errors.startAt}>
              <Input value={startAt} onChange={(event) => setStartAt(event.target.value)} aria-required="true" />
            </Field>
            <Field label="Bitiş" error={errors.endAt}>
              <Input value={endAt} onChange={(event) => setEndAt(event.target.value)} aria-required="true" />
            </Field>
            <Field label="İlk sermaye" error={errors.initialCash}>
              <Input value={initialCash} onChange={(event) => setInitialCash(event.target.value)} aria-required="true" />
            </Field>
            <Field label="Veri kaynağı" error={errors.dataSource}>
              <Input value={dataSource} onChange={(event) => setDataSource(event.target.value)} aria-required="true" />
            </Field>
          </div>
          <Field label="Parametreler JSON" error={errors.parameters}>
            <textarea
              className="min-h-28 w-full rounded-md border border-border p-3 text-sm outline-none focus:ring-2 focus:ring-primary/30"
              value={parameters}
              onChange={(event) => setParameters(event.target.value)}
              aria-required="true"
            />
          </Field>
          <Button onClick={submit} disabled={submitting}>
            <Play size={16} /> {submitting ? "Çalışıyor..." : "Backtest Başlat"}
          </Button>
        </Card>
      </section>
    </main>
  );
}

function Field({
  label,
  children,
  error,
}: {
  label: string;
  children: React.ReactNode;
  error?: string;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-muted">{label}</span>
      {children}
      {error && <span className="mt-1 block text-xs text-danger">{error}</span>}
    </label>
  );
}
