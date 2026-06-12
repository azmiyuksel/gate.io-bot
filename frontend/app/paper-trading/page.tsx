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
import { getAccessToken } from "@/lib/auth-api";
import { money } from "@/lib/utils";
import {
  getPaperEquity,
  getPaperPositions,
  getPaperRiskStatus,
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
  PaperStatus,
  PaperTrade,
} from "@/types/paper";

/* ───────────────────────────── Page ───────────────────────────── */

export default function PaperTradingPage() {
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [equity, setEquity] = useState<PaperEquityPoint[]>([]);
  const [risk, setRisk] = useState<PaperRiskStatus | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  const refresh = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [s, p, t, e, r] = await Promise.all([
        getPaperStatus(),
        getPaperPositions(),
        getPaperTrades(),
        getPaperEquity(),
        getPaperRiskStatus(),
      ]);
      if (s) setStatus(s);
      setPositions(p);
      setTrades(t);
      setEquity(e);
      if (r) setRisk(r);
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

  async function action(fn: () => Promise<boolean>) {
    setActionLoading(true);
    await fn();
    await refresh();
    setActionLoading(false);
  }

  const botStatus = status?.status ?? "STOPPED";

  /* ── Equity chart data ── */
  const equityChartData = equity.map((p) => ({
    time: new Date(p.timestamp).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }),
    equity: p.equity,
    drawdown: Math.abs(p.drawdown) * 100,
  }));

  /* ── Daily PnL from trades ── */
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
      {/* ─── Header ─── */}
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold">Paper Trading</h1>
            <p className="text-sm text-muted">Sanal canlı işlem simülasyonu</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={botStatus} />
            <Button onClick={refresh} disabled={loading || !token}>
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} /> Yenile
            </Button>
          </div>
        </div>
        {/* Action buttons */}
        {token && (
          <div className="mx-auto flex max-w-7xl flex-wrap gap-2 px-6 pb-4">
            {botStatus === "STOPPED" && (
              <Button onClick={() => action(startPaperTrading)} disabled={actionLoading}>
                <Play size={15} /> Başlat
              </Button>
            )}
            {botStatus === "RUNNING" && (
              <>
                <Button onClick={() => action(pausePaperTrading)} disabled={actionLoading} className="bg-amber-600">
                  <CirclePause size={15} /> Duraklat
                </Button>
                <Button onClick={() => action(stopPaperTrading)} disabled={actionLoading} className="bg-danger">
                  <Square size={15} /> Durdur
                </Button>
              </>
            )}
            {botStatus === "PAUSED" && (
              <>
                <Button onClick={() => action(resumePaperTrading)} disabled={actionLoading}>
                  <Play size={15} /> Devam Et
                </Button>
                <Button onClick={() => action(stopPaperTrading)} disabled={actionLoading} className="bg-danger">
                  <Square size={15} /> Durdur
                </Button>
              </>
            )}
            <Button
              onClick={() => {
                if (confirm("Tüm paper trading verileri sıfırlanacak. Emin misiniz?")) action(resetPaperTrading);
              }}
              disabled={actionLoading}
              className="bg-foreground/80"
            >
              <RotateCcw size={15} /> Sıfırla
            </Button>
          </div>
        )}
      </header>

      {/* ─── Metric Cards ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Equity"
          value={`$${money(status?.equity ?? 0)}`}
          icon={<Activity size={18} />}
        />
        <Metric
          label="Realized PnL"
          value={`$${money(status?.realized_pnl ?? 0)}`}
          icon={Number(status?.realized_pnl ?? 0) >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
          color={Number(status?.realized_pnl ?? 0) >= 0 ? "#146c5d" : "#b42318"}
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
          color="#b42318"
        />
      </section>

      {/* ─── Charts ─── */}
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

      {/* ─── Positions + Risk ─── */}
      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        {/* Open Positions */}
        <Card>
          <h2 className="mb-4 text-base font-semibold">Açık Pozisyonlar</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2">Sembol</th>
                  <th>Miktar</th>
                  <th>Giriş</th>
                  <th>Güncel</th>
                  <th>PnL</th>
                  <th>Stop</th>
                  <th>Hedef</th>
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
                      <td className="text-muted">-</td>
                      <td className="text-muted">-</td>
                    </tr>
                  );
                })}
                {positions.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted" colSpan={7}>
                      Açık pozisyon yok.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Risk Status */}
        <Card>
          <div className="mb-4 flex items-center gap-2">
            <ShieldAlert size={17} />
            <h2 className="text-base font-semibold">Risk Durumu</h2>
          </div>
          {risk ? (
            <div className="space-y-5">
              <RiskItem
                label="Günlük Zarar"
                current={risk.current_daily_loss_pct * 100}
                max={risk.max_daily_loss_pct * 100}
                unit="%"
                color={risk.current_daily_loss_pct / risk.max_daily_loss_pct > 0.7 ? "#b42318" : "#146c5d"}
              />
              <RiskItem
                label="Drawdown"
                current={risk.current_drawdown * 100}
                max={risk.max_drawdown_pct * 100}
                unit="%"
                color={risk.current_drawdown / risk.max_drawdown_pct > 0.7 ? "#b42318" : "#146c5d"}
              />
              <RiskItem
                label="Exposure"
                current={risk.current_exposure * 100}
                max={risk.max_exposure_pct * 100}
                unit="%"
                color={risk.current_exposure / risk.max_exposure_pct > 0.7 ? "#b42318" : "#146c5d"}
              />
              <RiskItem
                label="Açık Pozisyon"
                current={risk.current_open_positions}
                max={risk.max_open_positions}
                unit=""
                color={risk.current_open_positions >= risk.max_open_positions ? "#b42318" : "#146c5d"}
              />
            </div>
          ) : (
            <p className="text-sm text-muted">Risk verisi yok.</p>
          )}
        </Card>
      </section>

      {/* ─── Recent Trades ─── */}
      <section className="mx-auto max-w-7xl px-6 pb-10">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Son İşlemler</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2">Zaman</th>
                  <th>Sembol</th>
                  <th>Yön</th>
                  <th>Fiyat</th>
                  <th>Miktar</th>
                  <th>Ücret</th>
                  <th>PnL</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => {
                  const pnl = Number(trade.realized_pnl);
                  return (
                    <tr key={trade.id} className="border-b border-border">
                      <td className="py-3 text-muted">
                        {new Date(trade.traded_at).toLocaleString("tr-TR", {
                          day: "2-digit",
                          month: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td className="font-medium">{trade.symbol}</td>
                      <td>
                        <span
                          className={`inline-block rounded px-2 py-0.5 text-xs font-semibold uppercase text-white ${
                            trade.side === "buy" ? "bg-primary" : "bg-danger"
                          }`}
                        >
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
                    <td className="py-6 text-muted" colSpan={7}>
                      İşlem geçmişi yok.
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

/* ───────────────────── Sub-components ───────────────────── */

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

function Metric({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  color?: string;
}) {
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between text-muted">
        <span className="text-sm">{label}</span>
        {icon}
      </div>
      <div className="text-2xl font-semibold" style={color ? { color } : undefined}>
        {value}
      </div>
    </Card>
  );
}

function RiskItem({
  label,
  current,
  max,
  unit,
  color,
}: {
  label: string;
  current: number;
  max: number;
  unit: string;
  color: string;
}) {
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
        <div
          className="h-2 rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}
