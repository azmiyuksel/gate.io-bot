"use client";

import Link from "next/link";
import { Activity, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { Pagination, usePagination } from "@/components/ui/pagination";
import { TableSkeleton } from "@/components/ui/skeleton";
import { money } from "@/lib/utils";
import { authFetch, getAccessToken } from "@/lib/auth-api";
import type { BacktestListItem } from "@/types/backtest";

export function BacktestList() {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [runs, setRuns] = useState<BacktestListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const { page, setPage, totalPages, paginatedItems } = usePagination(runs, 10);

  async function refresh() {
    if (!token) return;
    setLoading(true);
    try {
      const response = await authFetch(`/backtests`);
      if (response.ok) {
        setRuns(await response.json());
      } else {
        toast("Backtest listesi alınamadı", "error");
      }
    } catch {
      toast("Sunucuya ulaşılamadı", "error");
    } finally {
      setLoading(false);
    }
  }

  async function remove(id: number) {
    const res = await authFetch(`/backtests/${id}`, { method: "DELETE" });
    if (res.ok) {
      toast("Backtest silindi", "success");
      await refresh();
    } else {
      toast("Backtest silinemedi", "error");
    }
    setConfirmDelete(null);
  }

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  useEffect(() => {
    refresh();
  }, [token]);

  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <Breadcrumb items={[{ label: "Backtest" }]} />
            <h1 className="mt-2 text-xl font-semibold">Backtests</h1>
            <p className="text-sm text-muted">Strateji performansını geçmiş veri üzerinde karşılaştır</p>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={refresh} disabled={loading}>
              <Activity size={16} /> Yenile
            </Button>
            <Link href="/backtests/create">
              <Button><Plus size={16} /> Yeni</Button>
            </Link>
          </div>
        </div>
      </header>

      <section className="mx-auto px-6 py-6 max-w-7xl">
        {loading ? (
          <TableSkeleton rows={5} cols={7} />
        ) : (
          <>
            <Card>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm" role="table">
                  <thead className="border-b border-border text-muted">
                    <tr>
                      <th className="py-2" scope="col">Tarih</th>
                      <th scope="col">Strateji</th>
                      <th scope="col">Sembol</th>
                      <th scope="col">Net Kar</th>
                      <th scope="col">Sharpe</th>
                      <th scope="col">Max DD</th>
                      <th scope="col">Durum</th>
                      <th scope="col"><span className="sr-only">İşlem</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedItems.map((run) => (
                      <tr key={run.id} className="border-b border-border">
                        <td className="py-3">{new Date(run.created_at).toLocaleString()}</td>
                        <td>{run.strategy_name}</td>
                        <td>{run.symbol} · {run.timeframe}</td>
                        <td>${money(run.net_profit)}</td>
                        <td>{run.sharpe_ratio.toFixed(2)}</td>
                        <td>{(run.max_drawdown * 100).toFixed(2)}%</td>
                        <td>{run.status}</td>
                        <td className="flex justify-end gap-2 py-2">
                          <Link href={`/backtests/results/${run.id}`}>
                            <Button className="px-3">Aç</Button>
                          </Link>
                          <Button
                            className="bg-danger px-3"
                            onClick={() => setConfirmDelete(run.id)}
                            aria-label={`Backtest #${run.id} sil`}
                          >
                            <Trash2 size={16} />
                          </Button>
                        </td>
                      </tr>
                    ))}
                    {runs.length === 0 && (
                      <tr>
                        <td className="py-6 text-muted" colSpan={8}>Henüz backtest yok.</td>
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
        title="Backtest'i Sil"
        message="Bu backtest'i silmek istediğinize emin misiniz? Bu işlem geri alınamaz."
        confirmLabel="Sil"
        danger
        onConfirm={() => confirmDelete && remove(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </main>
  );
}
