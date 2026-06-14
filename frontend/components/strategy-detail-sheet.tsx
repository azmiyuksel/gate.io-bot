"use client";

import { X, TrendingUp, Activity, BarChart3, Gauge } from "lucide-react";
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getStrategyDetail } from "@/lib/strategy-research-api";
import type { StrategyDetail } from "@/types/strategy-research";

function num(v: string | number | null | undefined): number {
  if (v === null || v === undefined) return 0;
  return typeof v === "number" ? v : Number(v);
}

interface Props {
  strategyId: number;
  strategyName: string;
  open: boolean;
  onClose: () => void;
}

export default function StrategyDetailSheet({ strategyId, strategyName, open, onClose }: Props) {
  const [detail, setDetail] = useState<StrategyDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !strategyId) return;
    setLoading(true);
    getStrategyDetail(strategyId).then((d) => {
      setDetail(d);
      setLoading(false);
    });
  }, [open, strategyId]);

  if (!open) return null;

  const bestVersion = detail?.versions?.[0];
  const params = bestVersion?.parameters ?? detail?.strategy?.parameters ?? {};
  const equityData =
    detail?.equity_curve && detail.equity_curve.length > 0
      ? detail.equity_curve.map((pt: Record<string, unknown>) => ({
          index: pt.index ?? pt.idx ?? 0,
          equity: Number(pt.equity ?? pt.value ?? 0),
        }))
      : [];

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/30" onClick={onClose} />
      <div className="fixed right-0 top-0 z-50 flex h-full w-full max-w-xl flex-col border-l border-border bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold">{strategyName}</h2>
            <p className="text-xs text-muted-foreground">
              {detail?.strategy.template ?? "—"} | Status: {detail?.strategy.status ?? "—"}
            </p>
          </div>
          <button onClick={onClose} className="rounded p-1 hover:bg-neutral-100">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {loading && (
            <div className="flex items-center justify-center py-20 text-sm text-muted-foreground">
              Yükleniyor...
            </div>
          )}

          {!loading && detail && (
            <>
              <section>
                <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-neutral-700">
                  <Activity className="h-4 w-4" /> Parametreler
                </h3>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                  {Object.entries(params).map(([k, v]) => (
                    <div key={k} className="flex justify-between border-b border-neutral-100 py-1">
                      <span className="text-neutral-500">{k}</span>
                      <span className="font-mono font-medium">
                        {typeof v === "number" ? v.toFixed(v % 1 === 0 ? 0 : 3) : String(v)}
                      </span>
                    </div>
                  ))}
                </div>
              </section>

              {bestVersion && (
                <section>
                  <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-neutral-700">
                    <Gauge className="h-4 w-4" /> Metrikler
                  </h3>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    {[
                      ["Sharpe", num(bestVersion.sharpe).toFixed(3)],
                      ["Fitness", num(bestVersion.fitness).toFixed(3)],
                      ["Profit Factor", num(bestVersion.profit_factor).toFixed(3)],
                      ["Max DD", `${(num(bestVersion.max_drawdown) * 100).toFixed(1)}%`],
                      ["Stability", num(bestVersion.stability_score).toFixed(3)],
                      ["Consistency", num(bestVersion.consistency_score).toFixed(3)],
                      ["Total Trades", String(bestVersion.total_trades)],
                      ["Overfit", bestVersion.overfit ? "EVET" : "Hayır"],
                    ].map(([label, value]) => (
                      <div
                        key={label}
                        className="flex flex-col rounded border border-border bg-neutral-50 px-3 py-2"
                      >
                        <span className="text-xs text-neutral-500">{label}</span>
                        <span className="font-semibold">{value}</span>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {equityData.length > 0 && (
                <section>
                  <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-neutral-700">
                    <TrendingUp className="h-4 w-4" /> Equity Curve
                  </h3>
                  <div className="rounded border border-border bg-white p-2">
                    <ResponsiveContainer width="100%" height={180}>
                      <AreaChart data={equityData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                        <XAxis dataKey="index" hide />
                        <YAxis fontSize={10} />
                        <Tooltip />
                        <Area
                          type="monotone"
                          dataKey="equity"
                          stroke="#146c5d"
                          fill="#146c5d22"
                          strokeWidth={2}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </section>
              )}

              {detail.trades && detail.trades.length > 0 && (
                <section>
                  <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-neutral-700">
                    <BarChart3 className="h-4 w-4" /> Son Trade'ler
                  </h3>
                  <div className="max-h-48 overflow-y-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="text-neutral-500">
                        <tr className="border-b">
                          <th className="py-1 pr-2">Tarih</th>
                          <th className="py-1 pr-2">Yön</th>
                          <th className="py-1 pr-2">PnL</th>
                          <th className="py-1">Sebep</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.trades.slice(-15).map((t: Record<string, unknown>, i: number) => (
                          <tr key={i} className="border-b last:border-0">
                            <td className="py-1 pr-2 whitespace-nowrap">
                              {t.exit_time ? String(t.exit_time).slice(0, 10) : "—"}
                            </td>
                            <td className="py-1 pr-2">{String(t.side ?? "—")}</td>
                            <td
                              className={`py-1 pr-2 ${
                                Number(t.pnl ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"
                              }`}
                            >
                              {Number(t.pnl ?? 0).toFixed(2)}
                            </td>
                            <td className="py-1 text-neutral-500">{String(t.exit_reason ?? "—")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {detail.versions.length > 1 && (
                <section>
                  <h3 className="mb-2 text-sm font-semibold text-neutral-700">Versiyon Geçmişi</h3>
                  <div className="max-h-40 overflow-y-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="text-neutral-500">
                        <tr className="border-b">
                          <th className="py-1 pr-2">v</th>
                          <th className="py-1 pr-2">Fitness</th>
                          <th className="py-1 pr-2">Sharpe</th>
                          <th className="py-1 pr-2">DD</th>
                          <th className="py-1">Tarih</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.versions.map((v) => (
                          <tr key={v.id} className="border-b last:border-0">
                            <td className="py-1 pr-2">{v.version}</td>
                            <td className="py-1 pr-2">{num(v.fitness).toFixed(3)}</td>
                            <td className="py-1 pr-2">{num(v.sharpe).toFixed(2)}</td>
                            <td className="py-1 pr-2">{(num(v.max_drawdown) * 100).toFixed(1)}%</td>
                            <td className="py-1 whitespace-nowrap text-neutral-500">
                              {new Date(v.created_at).toLocaleDateString("tr-TR")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )}

          {!loading && !detail && (
            <div className="flex items-center justify-center py-20 text-sm text-neutral-400">
              Detay yüklenemedi.
            </div>
          )}
        </div>
      </div>
    </>
  );
}
