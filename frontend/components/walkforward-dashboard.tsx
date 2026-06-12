"use client";

import Link from "next/link";
import { Activity, Play, Settings, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Metric } from "@/components/ui/metric";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { Pagination, usePagination } from "@/components/ui/pagination";
import { TableSkeleton } from "@/components/ui/skeleton";
import { authFetch, getAccessToken } from "@/lib/auth-api";
import type { WalkForwardListItem } from "@/types/walkforward";

export function WalkForwardDashboard() {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [runs, setRuns] = useState<WalkForwardListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [symbol, setSymbol] = useState("BTC_USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [startDate, setStartDate] = useState("2022-01-01T00:00:00Z");
  const [endDate, setEndDate] = useState("2025-12-31T23:59:59Z");
  const [trainDays, setTrainDays] = useState("365");
  const [testDays, setTestDays] = useState("90");
  const [stepDays, setStepDays] = useState("90");
  const [nTrials, setNTrials] = useState("30");
  const [showSettings, setShowSettings] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const { page, setPage, totalPages, paginatedItems } = usePagination(runs, 10);

  async function refresh() {
    if (!token) return;
    setLoading(true);
    try {
      const response = await authFetch(`/walkforward`);
      if (response.ok) {
        setRuns(await response.json());
      } else {
        toast("Walk-forward listesi alınamadı", "error");
      }
    } catch {
      toast("Sunucuya ulaşılamadı", "error");
    } finally {
      setLoading(false);
    }
  }

  async function start() {
    const response = await authFetch(`/walkforward/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol,
        timeframe,
        mode: "rolling",
        start_at: startDate,
        end_at: endDate,
        train_period_days: Number(trainDays),
        test_period_days: Number(testDays),
        step_days: Number(stepDays),
        n_trials: Number(nTrials),
        data_source: "cache",
      }),
    });
    if (response.ok) {
      toast("Walk-forward analizi başlatıldı", "success");
      await refresh();
    } else {
      toast("Analiz başlatılamadı", "error");
    }
  }

  async function remove(id: number) {
    await authFetch(`/walkforward/${id}`, { method: "DELETE" });
    toast("Walk-forward silindi", "success");
    await refresh();
    setConfirmDelete(null);
  }

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  useEffect(() => {
    refresh();
  }, [token]);

  const latest = runs[0];

  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <Breadcrumb items={[{ label: "Walk-Forward" }]} />
            <h1 className="mt-2 text-xl font-semibold">Walk-Forward Analysis</h1>
            <p className="text-sm text-muted">Out-of-sample dayanıklılık ve overfit kontrol paneli</p>
          </div>
          <div className="flex items-center gap-3">
            <Button className="bg-transparent text-foreground hover:bg-border/60" onClick={() => setShowSettings(!showSettings)}>
              <Settings size={16} /> Parametreler
            </Button>
            <Button onClick={start}><Play size={16} /> Başlat</Button>
            <Button onClick={refresh} disabled={loading}><Activity size={16} /> Yenile</Button>
          </div>
        </div>
      </header>

      {showSettings && (
        <section className="border-b border-border bg-white">
          <div className="mx-auto grid max-w-7xl gap-4 px-6 py-4 sm:grid-cols-2 lg:grid-cols-4">
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Sembol</span>
              <Input value={symbol} onChange={(event) => setSymbol(event.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Timeframe</span>
              <Input value={timeframe} onChange={(event) => setTimeframe(event.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Başlangıç</span>
              <Input value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Bitiş</span>
              <Input value={endDate} onChange={(event) => setEndDate(event.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Eğitim periyodu (gün)</span>
              <Input value={trainDays} onChange={(event) => setTrainDays(event.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Test periyodu (gün)</span>
              <Input value={testDays} onChange={(event) => setTestDays(event.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Adım (gün)</span>
              <Input value={stepDays} onChange={(event) => setStepDays(event.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-muted">Deneme sayısı</span>
              <Input value={nTrials} onChange={(event) => setNTrials(event.target.value)} />
            </label>
          </div>
        </section>
      )}

      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-3 lg:grid-cols-5">
        <Metric label="Robustness" value={(latest?.robustness_score ?? 0).toFixed(1)} />
        <Metric label="WFE" value={`${((latest?.wfe ?? 0) * 100).toFixed(1)}%`} />
        <Metric label="Consistency" value={`${((latest?.consistency_score ?? 0) * 100).toFixed(1)}%`} />
        <Metric label="Avg Sharpe" value={(latest?.average_sharpe ?? 0).toFixed(2)} />
        <Metric label="Avg Drawdown" value={`${((latest?.average_drawdown ?? 0) * 100).toFixed(2)}%`} />
      </section>

      <section className="mx-auto max-w-7xl px-6 pb-10">
        {loading ? (
          <TableSkeleton rows={5} cols={8} />
        ) : (
          <>
            <Card>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm" role="table">
                  <thead className="border-b border-border text-muted">
                    <tr>
                      <th className="py-2" scope="col">Tarih</th>
                      <th scope="col">Sembol</th>
                      <th scope="col">Mode</th>
                      <th scope="col">Robustness</th>
                      <th scope="col">WFE</th>
                      <th scope="col">Consistency</th>
                      <th scope="col">Karar</th>
                      <th scope="col"><span className="sr-only">İşlem</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedItems.map((run) => (
                      <tr key={run.id} className="border-b border-border">
                        <td className="py-3">{new Date(run.created_at).toLocaleString()}</td>
                        <td>{run.symbol} · {run.timeframe}</td>
                        <td>{run.mode}</td>
                        <td>{run.robustness_score.toFixed(1)}</td>
                        <td>{(run.wfe * 100).toFixed(1)}%</td>
                        <td>{(run.consistency_score * 100).toFixed(1)}%</td>
                        <td>{run.deployment_decision}</td>
                        <td className="flex justify-end gap-2 py-2">
                          <Link href={`/walk-forward/${run.id}`}>
                            <Button className="px-3">Detay</Button>
                          </Link>
                          <Button
                            className="bg-danger px-3"
                            onClick={() => setConfirmDelete(run.id)}
                            aria-label={`Walk-forward #${run.id} sil`}
                          >
                            <Trash2 size={16} />
                          </Button>
                        </td>
                      </tr>
                    ))}
                    {runs.length === 0 && (
                      <tr>
                        <td className="py-6 text-muted" colSpan={8}>Henüz walk-forward analizi yok.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </Card>
            <div className="mt-4 flex justify-center">
              <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
            </div>
          </>
        )}
      </section>

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Walk-Forward'i Sil"
        message="Bu walk-forward analizini silmek istediğinize emin misiniz?"
        confirmLabel="Sil"
        danger
        onConfirm={() => confirmDelete && remove(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </main>
  );
}
