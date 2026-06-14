"use client";

import {
  Activity,
  BarChart3,
  CirclePause,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Square,
  TrendingDown,
  TrendingUp,
  Trophy,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Metric } from "@/components/ui/metric";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { LastUpdated } from "@/components/ui/last-updated";
import { useToast } from "@/components/ui/toast";
import { getAccessToken } from "@/lib/auth-api";
import { money } from "@/lib/utils";
import {
  getPaperEquity,
  getPaperPositions,
  getPaperRiskStatus,
  getPaperSignalDiagnostics,
  getPaperStatus,
  getPaperTrades,
  pausePaperTrading,
  resetPaperTrading,
  resumePaperTrading,
  startPaperTrading,
  stopPaperTrading,
} from "@/lib/paper-api";
import type {
  PaperEquityPoint,
  PaperPosition,
  PaperRiskStatus,
  PaperSignalDiagnostics,
  PaperStatus,
  PaperTrade,
} from "@/types/paper";

export default function PaperTradingPage() {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [equity, setEquity] = useState<PaperEquityPoint[]>([]);
  const [risk, setRisk] = useState<PaperRiskStatus | null>(null);
  const [diagnostics, setDiagnostics] = useState<PaperSignalDiagnostics | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [s, p, t, e, r, d] = await Promise.all([
        getPaperStatus(),
        getPaperPositions(),
        getPaperTrades(),
        getPaperEquity(),
        getPaperRiskStatus(),
        getPaperSignalDiagnostics(),
      ]);
      if (s) setStatus(s);
      setPositions(p);
      setTrades(t);
      setEquity(e);
      if (r) setRisk(r);
      setDiagnostics(d);
      setLastUpdated(new Date());
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    if (!token) return;
    refresh();
    intervalRef.current = setInterval(refresh, 5000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [token, refresh]);

  async function action(fn: () => Promise<boolean>, successMsg: string) {
    setActionLoading(true);
    const ok = await fn();
    if (ok) toast(successMsg, "success");
    else toast("İşlem başarısız", "error");
    await refresh();
    setActionLoading(false);
  }

  const botStatus = status?.status ?? "STOPPED";

  const equityChartData = equity.map((p) => ({
    time: new Date(p.timestamp).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
    equity: p.equity,
    drawdown: Math.abs(p.drawdown) * 100,
  }));

  const dailyPnl = trades.reduce((acc, t) => {
    const day = new Date(t.traded_at).toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" });
    acc[day] = (acc[day] || 0) + Number(t.realized_pnl);
    return acc;
  }, {} as Record<string, number>);
  const dailyPnlData = Object.entries(dailyPnl)
    .slice(-14)
    .map(([date, pnl]) => ({ date, pnl: Number(pnl.toFixed(2)) }));

  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <Breadcrumb items={[{ label: "Paper Trading" }]} />
            <h1 className="mt-2 text-xl font-semibold">Paper Trading</h1>
            <p className="text-sm text-muted">Sanal canlı işlem simülasyonu</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={botStatus} />
            <LastUpdated time={lastUpdated} onRefresh={refresh} loading={loading} />
          </div>
        </div>
        {token && (
          <div className="mx-auto flex max-w-7xl flex-wrap gap-2 px-6 pb-4">
            {botStatus === "STOPPED" && (
              <Button onClick={() => action(startPaperTrading, "Paper trading başlatıldı")} disabled={actionLoading}>
                <Play size={15} /> Başlat
              </Button>
            )}
            {botStatus === "RUNNING" && (
              <>
                <Button onClick={() => action(pausePaperTrading, "Duraklatıldı")} disabled={actionLoading} className="bg-amber-600">
                  <CirclePause size={15} /> Duraklat
                </Button>
                <Button onClick={() => action(stopPaperTrading, "Durduruldu")} disabled={actionLoading} className="bg-danger">
                  <Square size={15} /> Durdur
                </Button>
              </>
            )}
            {botStatus === "PAUSED" && (
              <>
                <Button onClick={() => action(resumePaperTrading, "Devam ediliyor")} disabled={actionLoading}>
                  <Play size={15} /> Devam Et
                </Button>
                <Button onClick={() => action(stopPaperTrading, "Durduruldu")} disabled={actionLoading} className="bg-danger">
                  <Square size={15} /> Durdur
                </Button>
              </>
            )}
            <Button onClick={() => setConfirmReset(true)} disabled={actionLoading} className="bg-foreground/80">
              <RotateCcw size={15} /> Sıfırla
            </Button>
          </div>
        )}
      </header>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Equity" value={`$${money(status?.equity ?? 0)}`} icon={<Activity size={18} />} />
        <Metric
          label="Realized PnL"
          value={`$${money(status?.realized_pnl ?? 0)}`}
          icon={Number(status?.realized_pnl ?? 0) >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
        />
        <Metric
          label="Win Rate"
          value={`${((status?.metrics?.win_rate_rolling_100 ?? 0) * 100).toFixed(1)}%`}
          icon={<Trophy size={18} />}
        />
        <Metric
          label="Max Drawdown"
          value={`${(Math.abs(status?.metrics?.drawdown ?? 0) * 100).toFixed(2)}%`}
          icon={<ShieldAlert size={18} />}
        />
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Equity Curve</h2>
            <span className="text-sm text-muted">
              Sharpe {(status?.metrics?.rolling_sharpe ?? 0).toFixed(2)}
            </span>
          </div>
          <div className="h-72">
            {equityChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={equityChartData}>
                  <CartesianGrid stroke="#ecece7" />
                  <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
                  <Tooltip formatter={(v: number) => `$${money(v)}`} />
                  <Area type="monotone" dataKey="equity" stroke="#146c5d" fill="#146c5d33" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">Equity verisi yok.</div>
            )}
          </div>
        </Card>

        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Günlük PnL</h2>
            <BarChart3 size={16} className="text-muted" />
          </div>
          <div className="h-72">
            {dailyPnlData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dailyPnlData}>
                  <CartesianGrid stroke="#ecece7" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v: number) => `$${v.toFixed(2)}`} />
                  <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                    {dailyPnlData.map((entry, i) => (
                      <Cell key={i} fill={entry.pnl >= 0 ? "#146c5d" : "#b42318"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-muted">İşlem verisi yok.</div>
            )}
          </div>
        </Card>
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Açık Pozisyonlar</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" role="table">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2" scope="col">Sembol</th>
                  <th scope="col">Miktar</th>
                  <th scope="col">Giriş</th>
                  <th scope="col">Güncel</th>
                  <th scope="col">PnL</th>
                  <th scope="col">Stop</th>
                  <th scope="col">Hedef</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => {
                  const pnl = Number(pos.unrealized_pnl);
                  return (
                    <tr key={pos.id} className="border-b border-border">
                      <td className="py-3 font-medium">{pos.symbol}</td>
                      <td>{money(pos.quantity)}</td>
                      <td>${money(pos.average_entry_price)}</td>
                      <td>${money(pos.last_price)}</td>
                      <td className={pnl >= 0 ? "text-primary font-medium" : "text-danger font-medium"}>
                        ${money(pos.unrealized_pnl)}
                      </td>
                      <td className={pos.stop_loss ? "text-danger" : "text-muted"}>
                        {pos.stop_loss ? `$${money(pos.stop_loss)}` : "-"}
                      </td>
                      <td className={pos.take_profit ? "text-primary" : "text-muted"}>
                        {pos.take_profit ? `$${money(pos.take_profit)}` : "-"}
                      </td>
                    </tr>
                  );
                })}
                {positions.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted" colSpan={7}>Açık pozisyon yok.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <div className="mb-4 flex items-center gap-2">
            <ShieldAlert size={17} />
            <h2 className="text-base font-semibold">Risk Durumu</h2>
          </div>
          {risk ? (
            <div className="space-y-5">
              <RiskItem label="Günlük Zarar" current={risk.current_daily_loss_pct * 100} max={risk.max_daily_loss_pct * 100} unit="%" color={risk.current_daily_loss_pct / risk.max_daily_loss_pct > 0.7 ? "#b42318" : "#146c5d"} />
              <RiskItem label="Drawdown" current={risk.current_drawdown * 100} max={risk.max_drawdown_pct * 100} unit="%" color={risk.current_drawdown / risk.max_drawdown_pct > 0.7 ? "#b42318" : "#146c5d"} />
              <RiskItem label="Exposure" current={risk.current_exposure * 100} max={risk.max_exposure_pct * 100} unit="%" color={risk.current_exposure / risk.max_exposure_pct > 0.7 ? "#b42318" : "#146c5d"} />
              <RiskItem label="Açık Pozisyon" current={risk.current_open_positions} max={risk.max_open_positions} unit="" color={risk.current_open_positions >= risk.max_open_positions ? "#b42318" : "#146c5d"} />
            </div>
          ) : (
            <p className="text-sm text-muted">Risk verisi yok.</p>
          )}
        </Card>
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[1fr_1fr]">
        <Card>
          <div className="mb-1 flex items-center gap-2">
            <Activity size={17} />
            <h2 className="text-base font-semibold">Sinyal Tanılama</h2>
          </div>
          <p className="mb-2 text-sm text-muted">
            Son {diagnostics?.window_hours ?? 24} saatte girişlerin neden atlandığı
            {diagnostics ? ` (${diagnostics.evaluations} değerlendirme)` : ""}.
          </p>
          {diagnostics && diagnostics.evaluations === 0 && (
            <div className="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
              Hiç değerlendirme kaydı yok. <strong>paper-worker</strong> servisi
              çalışmıyor olabilir veya worker dış ağa (Gate.io) erişemiyor olabilir.
              <code className="ml-1">docker compose logs -f paper-worker</code> ile kontrol edin.
            </div>
          )}
          {diagnostics?.last_evaluation_at && (
            <p className="mb-4 text-xs text-muted">
              Son değerlendirme:{" "}
              {new Date(diagnostics.last_evaluation_at).toLocaleString("tr-TR")}
            </p>
          )}
          {diagnostics && Object.keys(diagnostics.reason_counts).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(diagnostics.reason_counts).map(([reason, count]) => {
                const max = Math.max(...Object.values(diagnostics.reason_counts));
                const pct = max > 0 ? (count / max) * 100 : 0;
                const approved = reason === "approved";
                return (
                  <div key={reason}>
                    <div className="flex items-center justify-between text-sm">
                      <span className={approved ? "font-medium text-primary" : ""}>{reason}</span>
                      <span className="text-muted">{count}</span>
                    </div>
                    <div className="mt-1 h-1.5 w-full rounded bg-border">
                      <div
                        className="h-1.5 rounded"
                        style={{ width: `${pct}%`, backgroundColor: approved ? "#146c5d" : "#b9933a" }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted">Henüz değerlendirme kaydı yok.</p>
          )}
        </Card>

        <Card>
          <h2 className="mb-4 text-base font-semibold">Sembol Bazında Son Durum</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" role="table">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2" scope="col">Sembol</th>
                  <th scope="col">Son Neden</th>
                </tr>
              </thead>
              <tbody>
                {diagnostics && Object.keys(diagnostics.latest_by_symbol).length > 0 ? (
                  Object.entries(diagnostics.latest_by_symbol).map(([symbol, info]) => (
                    <tr key={symbol} className="border-b border-border">
                      <td className="py-3 font-medium">{symbol}</td>
                      <td className={info.reason === "approved" ? "text-primary font-medium" : "text-muted"}>
                        {info.reason}
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className="py-6 text-muted" colSpan={2}>Kayıt yok.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </section>

      <section className="mx-auto max-w-7xl px-6 pb-10">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Son İşlemler</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" role="table">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2" scope="col">Zaman</th>
                  <th scope="col">Sembol</th>
                  <th scope="col">Yön</th>
                  <th scope="col">Fiyat</th>
                  <th scope="col">Miktar</th>
                  <th scope="col">Ücret</th>
                  <th scope="col">PnL</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => {
                  const pnl = Number(trade.realized_pnl);
                  return (
                    <tr key={trade.id} className="border-b border-border">
                      <td className="py-3 text-muted">
                        {new Date(trade.traded_at).toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                      </td>
                      <td className="font-medium">{trade.symbol}</td>
                      <td>
                        <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold uppercase text-white ${trade.side === "buy" ? "bg-primary" : "bg-danger"}`}>
                          {trade.side === "buy" ? "AL" : "SAT"}
                        </span>
                      </td>
                      <td>${money(trade.price)}</td>
                      <td>{money(trade.quantity)}</td>
                      <td className="text-muted">${money(trade.fee)}</td>
                      <td className={pnl >= 0 ? "font-medium text-primary" : "font-medium text-danger"}>
                        ${money(trade.realized_pnl)}
                      </td>
                    </tr>
                  );
                })}
                {trades.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted" colSpan={7}>İşlem geçmişi yok.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </section>

      <ConfirmDialog
        open={confirmReset}
        title="Paper Trading'i Sıfırla"
        message="Tüm paper trading verileri sıfırlanacak. Emin misiniz?"
        confirmLabel="Sıfırla"
        danger
        onConfirm={() => {
          setConfirmReset(false);
          action(resetPaperTrading, "Sıfırlandı");
        }}
        onCancel={() => setConfirmReset(false)}
      />
    </main>
  );
}

function StatusBadge({ status }: { status: string }) {
  const config = {
    RUNNING: { bg: "bg-emerald-100 text-emerald-700", dot: "bg-emerald-500", label: "Çalışıyor" },
    PAUSED: { bg: "bg-amber-100 text-amber-700", dot: "bg-amber-500", label: "Duraklatıldı" },
    STOPPED: { bg: "bg-red-100 text-red-700", dot: "bg-red-500", label: "Durdu" },
  }[status] ?? { bg: "bg-gray-100 text-gray-700", dot: "bg-gray-500", label: status };

  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${config.bg}`}>
      <span className={`h-2 w-2 rounded-full ${config.dot} ${status === "RUNNING" ? "animate-pulse" : ""}`} />
      {config.label}
    </span>
  );
}

function RiskItem({ label, current, max, unit, color }: { label: string; current: number; max: number; unit: string; color: string }) {
  const pct = max > 0 ? Math.min((current / max) * 100, 100) : 0;
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-sm">
        <span className="text-muted">{label}</span>
        <span className="font-medium">
          {current.toFixed(unit === "%" ? 2 : 0)}{unit} / {max.toFixed(unit === "%" ? 2 : 0)}{unit}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-border">
        <div className="h-2 rounded-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}
