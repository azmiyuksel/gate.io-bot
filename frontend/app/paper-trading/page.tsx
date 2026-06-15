"use client";

import {
  Activity,
  BarChart3,
  CirclePause,
  PieChart,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Square,
  TrendingDown,
  TrendingUp,
  Trophy,
  X,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  PieChart as RePieChart,
  Pie,
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
import { fmtPrice, fmtQty, fmtUTC, fmtUTCShort, money } from "@/lib/utils";
import {
  closePaperPosition,
  createPaperStream,
  getPaperEconomics,
  getPaperEquity,
  getPaperExitStats,
  getPaperPositions,
  getPaperRiskStatus,
  getPaperSignalDiagnostics,
  getPaperStatus,
  getPaperTrades,
  manualPaperOrder,
  pausePaperTrading,
  resetPaperTrading,
  resumePaperTrading,
  startPaperTrading,
  stopPaperTrading,
} from "@/lib/paper-api";
import type {
  PaperEconomics,
  PaperEquityPoint,
  PaperPosition,
  PaperRiskStatus,
  PaperSignalDiagnostics,
  PaperStatus,
  PaperTrade,
} from "@/types/paper";

const EXIT_COLORS: Record<string, string> = {
  stop_loss: "#b42318",
  trailing_stop: "#d97706",
  take_profit: "#146c5d",
  manual_close: "#6366f1",
  signal_sell: "#0ea5e9",
  signal_cover: "#8b5cf6",
  manual_partial: "#ec4899",
};

export default function PaperTradingPage() {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionLoadingBtn, setActionLoadingBtn] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  const [status, setStatus] = useState<PaperStatus | null>(null);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [equity, setEquity] = useState<PaperEquityPoint[]>([]);
  const [risk, setRisk] = useState<PaperRiskStatus | null>(null);
  const [diagnostics, setDiagnostics] = useState<PaperSignalDiagnostics | null>(null);
  const [economics, setEconomics] = useState<PaperEconomics | null>(null);
  const [exitStats, setExitStats] = useState<Record<string, number> | null>(null);

  // Quick trade form
  const [quickSymbol, setQuickSymbol] = useState("BTC_USDT");
  const [quickSide, setQuickSide] = useState<"buy" | "sell">("buy");
  const [quickQty, setQuickQty] = useState("0.01");

  const sseRef = useRef<EventSource | null>(null);
  const lastTradeCount = useRef(0);
  const botStatusRef = useRef("STOPPED");

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  const fetchFast = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [s, p, t, r] = await Promise.all([
        getPaperStatus().catch(() => null),
        getPaperPositions().catch(() => []),
        getPaperTrades().catch(() => []),
        getPaperRiskStatus().catch(() => null),
      ]);
      if (s) setStatus(s);
      setPositions(p);
      setTrades(t);
      if (r) setRisk(r);
      setLastUpdated(new Date());
    } finally {
      setLoading(false);
    }
  }, [token]);

  const fetchSlow = useCallback(async () => {
    if (!token) return;
    const [e, d, ec, es] = await Promise.all([
      getPaperEquity().catch(() => []),
      getPaperSignalDiagnostics().catch(() => null),
      getPaperEconomics().catch(() => null),
      getPaperExitStats().catch(() => null),
    ]);
    setEquity(e);
    setDiagnostics(d);
    setEconomics(ec);
    setExitStats(es?.counts ?? null);
  }, [token]);

  const refresh = useCallback(async () => {
    await Promise.all([fetchFast(), fetchSlow()]);
  }, [fetchFast, fetchSlow]);

  // Sound alert on new trades
  useEffect(() => {
    if (trades.length > lastTradeCount.current && lastTradeCount.current > 0) {
      try {
        const audio = new Audio("data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACAf39/f4B/f3+Af4CAgH9/f3+Af4B/f3+Af39/gH9/f3+Af39/gIB/f3+Af39/gH+Af39/gH+Af3+Af3+Af3+Af39/gH+Af3+Af3+Af39/gH9/f3+Af3+Af3+Af39/gH9/f3+Af39/gH+Af39/gH+Af3+Af3+Af39/gH9/f3+Af39/gH+Af39/gH9/f3+Af39/gH+Af3+Af39/gH+Af39/gH+Af3+Af39/gH+Af3+Af39/gH+Af39/gH+Af39/gH+Af39/gH+Af39/gH+Af39/gH+Af39/gH+Af39/gH+Af39/gH+Af39/gH+Af39/gH+Af39/gH+Af39/gA==");
        audio.volume = 0.3;
        audio.play().catch(() => {});
      } catch {}
    }
    lastTradeCount.current = trades.length;
  }, [trades]);

  useEffect(() => {
    if (!token) return;
    fetchFast();
    fetchSlow();
    sseRef.current = createPaperStream((data) => {
      if (data) {
        setStatus(data);
        setLastUpdated(new Date());
      }
    });
    const fast = setInterval(fetchFast, 5000);
    const slow = setInterval(fetchSlow, 30000);
    return () => {
      if (sseRef.current) sseRef.current.close();
      clearInterval(fast);
      clearInterval(slow);
    };
  }, [token, fetchFast, fetchSlow]);

  // Keyboard shortcuts
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const s = e.key.toLowerCase();
      const st = botStatusRef.current;
      if (s === "s" && st === "STOPPED") action(() => startPaperTrading(), "Başlatıldı", "start");
      if (s === "p" && st === "RUNNING") action(() => pausePaperTrading(), "Duraklatıldı", "pause");
      if (s === "r" && st === "PAUSED") action(() => resumePaperTrading(), "Devam ediliyor", "resume");
      if (s === "x" && st !== "STOPPED") action(() => stopPaperTrading(), "Durduruldu", "stop");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function action(fn: () => Promise<boolean>, successMsg: string, btnId = "") {
    setActionLoadingBtn(btnId);
    let ok = false;
    try {
      ok = await fn();
    } catch (err) {
      toast(err instanceof Error ? err.message : "İşlem başarısız", "error");
      setActionLoadingBtn("");
      return;
    }
    setActionLoadingBtn("");
    toast(ok ? successMsg : "İşlem başarısız", ok ? "success" : "error");
    // Refresh fast data in background — don't block the button
    fetchFast();
  }

  const botStatus = status?.status ?? "STOPPED";
  botStatusRef.current = botStatus;

  const initialBalance = Number(status?.initial_balance ?? 0);
  const totalReturnPct =
    initialBalance > 0 ? ((Number(status?.equity ?? 0) - initialBalance) / initialBalance) * 100 : 0;

  // Trade markers on equity chart
  const tradeMarkers = trades
    .filter((t) => Number(t.realized_pnl) !== 0)
    .map((t) => ({
      time: fmtUTCShort(t.traded_at),
      equity: Number(t.price) * Number(t.quantity),
      pnl: Number(t.realized_pnl),
      symbol: t.symbol,
      side: t.side,
    }));

  const equityChartData = equity.map((p) => ({
    time: fmtUTCShort(p.timestamp),
    equity: p.equity,
  }));

  const dailyMap = trades.reduce((acc, t) => {
    const key = new Date(t.traded_at).toISOString().slice(0, 10);
    acc[key] = (acc[key] || 0) + Number(t.realized_pnl);
    return acc;
  }, {} as Record<string, number>);
  const dailyPnlData = Object.entries(dailyMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14)
    .map(([key, pnl]) => ({
      date: new Date(`${key}T00:00:00Z`).toLocaleDateString("en-GB", {
        timeZone: "UTC",
        day: "2-digit",
        month: "2-digit",
      }),
      pnl: Number(pnl.toFixed(2)),
    }));

  const maxReasonCount = diagnostics
    ? Math.max(1, ...Object.values(diagnostics.reason_counts))
    : 1;

  // Exit reason stats for pie chart
  const exitPieData = exitStats
    ? Object.entries(exitStats).map(([reason, count]) => ({ name: reason, value: count }))
    : [];

  const shortcuts = [
    { key: "S", label: "Başlat", when: "STOPPED" },
    { key: "P", label: "Duraklat", when: "RUNNING" },
    { key: "R", label: "Devam Et", when: "PAUSED" },
    { key: "X", label: "Durdur", when: "RUNNING/PAUSED" },
  ];

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
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-2 px-6 pb-4">
            {botStatus === "STOPPED" && (
              <Button onClick={() => action(() => startPaperTrading(), "Paper trading başlatıldı", "start")} disabled={!!actionLoadingBtn}>
                <Play size={15} /> Başlat [S]
              </Button>
            )}
            {botStatus === "RUNNING" && (
              <>
                <Button onClick={() => action(() => pausePaperTrading(), "Duraklatıldı", "pause")} disabled={!!actionLoadingBtn} className="bg-amber-600">
                  <CirclePause size={15} /> Duraklat [P]
                </Button>
                <Button onClick={() => action(() => stopPaperTrading(), "Durduruldu", "stop")} disabled={!!actionLoadingBtn} className="bg-danger">
                  <Square size={15} /> Durdur [X]
                </Button>
              </>
            )}
            {botStatus === "PAUSED" && (
              <>
                <Button onClick={() => action(() => resumePaperTrading(), "Devam ediliyor", "resume")} disabled={!!actionLoadingBtn}>
                  <Play size={15} /> Devam Et [R]
                </Button>
                <Button onClick={() => action(() => stopPaperTrading(), "Durduruldu", "stop")} disabled={!!actionLoadingBtn} className="bg-danger">
                  <Square size={15} /> Durdur [X]
                </Button>
              </>
            )}
            <Button onClick={() => setConfirmReset(true)} disabled={!!actionLoadingBtn} className="bg-foreground/80">
              <RotateCcw size={15} /> Sıfırla
            </Button>
          </div>
        )}
        {token && (
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-1 px-6 pb-3">
            <span className="text-xs text-muted">Kısayollar:</span>
            {shortcuts.map((s) => (
              <kbd key={s.key} className="rounded border border-border bg-gray-50 px-1.5 py-0.5 text-xs text-muted">
                {s.key}
              </kbd>
            ))}
          </div>
        )}
      </header>

      {!lastUpdated && (
        <div className="mx-auto max-w-7xl px-6 pt-4 text-sm text-muted">İlk veriler yükleniyor…</div>
      )}

      {botStatus === "PAUSED" && (
        <div className="mx-auto max-w-7xl px-6 pt-4">
          <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            Bot bir risk limiti nedeniyle <strong>duraklatıldı</strong>
            {status?.pause_reason ? ` (${status.pause_reason})` : ""} — bu yüzden ilk
            alımdan sonra yeni işlem açılmıyor. Devam etmek için yukarıdaki{" "}
            <strong>Devam Et</strong> butonunu kullanın.
          </div>
        </div>
      )}

      {/* Paper-Live parameter warning */}
      {botStatus === "RUNNING" && (
        <div className="mx-auto max-w-7xl px-6 pt-4">
          <div className="rounded border border-blue-200 bg-blue-50 p-2 text-xs text-blue-700">
            <strong>Paper mod:</strong> 15dk mum, 30sn değerlendirme. Strateji live ile aynı parametrelerde (RSI &lt; 35, trend filtresi açık, EMA20 mesafesi %1.5). Long + short sinyal üretir.
          </div>
        </div>
      )}

      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-5">
        <Metric label="Equity" value={`$${money(status?.equity ?? 0)}`} icon={<Activity size={18} />} />
        <Metric
          label="Toplam Getiri"
          value={`${totalReturnPct >= 0 ? "+" : ""}${totalReturnPct.toFixed(2)}%`}
          icon={totalReturnPct >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
        />
        <Metric
          label="Realized PnL"
          value={`$${money(status?.realized_pnl ?? 0)}`}
          icon={Number(status?.realized_pnl ?? 0) >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
        />
        <Metric
          label="Win Rate (son 100)"
          value={`${((status?.metrics?.win_rate_rolling_100 ?? 0) * 100).toFixed(1)}%`}
          icon={<Trophy size={18} />}
        />
        <Metric
          label="Max Drawdown"
          value={`${(Math.abs(status?.metrics?.drawdown ?? 0) * 100).toFixed(2)}%`}
          icon={<ShieldAlert size={18} />}
        />
      </section>

      {/* Quick Trade Panel */}
      {botStatus === "RUNNING" && (
        <section className="mx-auto max-w-7xl px-6 pb-6">
          <Card>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-1.5">
                <Zap size={16} className="text-amber-500" />
                <h3 className="text-sm font-semibold">Hızlı İşlem</h3>
              </div>
              <select
                value={quickSymbol}
                onChange={(e) => setQuickSymbol(e.target.value)}
                className="rounded border border-border px-2 py-1.5 text-sm"
              >
                {["BTC_USDT", "ETH_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT", "ADA_USDT", "LINK_USDT", "AVAX_USDT", "BNB_USDT", "DOT_USDT"].map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <select
                value={quickSide}
                onChange={(e) => setQuickSide(e.target.value as "buy" | "sell")}
                className="rounded border border-border px-2 py-1.5 text-sm"
              >
                <option value="buy">AL (Long)</option>
                <option value="sell">SAT (Short)</option>
              </select>
              <input
                type="text"
                value={quickQty}
                onChange={(e) => setQuickQty(e.target.value)}
                className="w-20 rounded border border-border px-2 py-1.5 text-sm"
                placeholder="0.01"
              />
              <Button
                className={`text-sm ${quickSide === "buy" ? "bg-primary" : "bg-danger"}`}
                onClick={() => {
                  const qty = parseFloat(quickQty);
                  if (isNaN(qty) || qty <= 0) {
                    toast("Geçerli bir miktar girin", "error");
                    return;
                  }
                  action(
                    () => manualPaperOrder(quickSymbol, quickSide, qty),
                    `${quickSide === "buy" ? "AL" : "SAT"} ${quickSymbol} ${qty}`,
                    "quick",
                  );
                }}
                disabled={!!actionLoadingBtn}
              >
                <Plus size={14} /> {quickSide === "buy" ? "AL" : "SAT"}
              </Button>
            </div>
          </Card>
        </section>
      )}

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Equity Curve</h2>
            <span className="text-sm text-muted">
              Sharpe (rolling) {(status?.metrics?.rolling_sharpe ?? 0).toFixed(2)}
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
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2" scope="col">Sembol</th>
                  <th scope="col">Yön</th>
                  <th scope="col">Miktar</th>
                  <th scope="col">Giriş</th>
                  <th scope="col">Güncel</th>
                  <th scope="col">PnL</th>
                  <th scope="col">PnL%</th>
                  <th scope="col">Stop</th>
                  <th scope="col">Hedef</th>
                  <th scope="col"></th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => {
                  const pnl = Number(pos.unrealized_pnl);
                  const cost = Number(pos.quantity) * Number(pos.average_entry_price);
                  const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;
                  return (
                    <tr key={pos.id} className="border-b border-border">
                      <td className="py-3 font-medium">{pos.symbol}</td>
                      <td>
                        <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold uppercase text-white ${pos.side === "sell" ? "bg-danger" : "bg-primary"}`}>
                          {pos.side === "sell" ? "SHORT" : "LONG"}
                        </span>
                      </td>
                      <td>{fmtQty(pos.quantity)}</td>
                      <td>${fmtPrice(pos.average_entry_price)}</td>
                      <td>${fmtPrice(pos.last_price)}</td>
                      <td className={pnl >= 0 ? "text-primary font-medium" : "text-danger font-medium"}>
                        ${money(pos.unrealized_pnl)}
                      </td>
                      <td className={pnlPct >= 0 ? "text-primary" : "text-danger"}>
                        {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%
                      </td>
                      <td className={pos.stop_loss ? "text-danger" : "text-muted"}>
                        {pos.stop_loss ? `$${fmtPrice(pos.stop_loss)}` : "-"}
                      </td>
                      <td className={pos.take_profit ? "text-primary" : "text-muted"}>
                        {pos.take_profit ? `$${fmtPrice(pos.take_profit)}` : "-"}
                      </td>
                      <td>
                        <button
                          onClick={() => action(() => closePaperPosition(pos.id), `${pos.symbol} kapatıldı`, `close-${pos.id}`)}
                          disabled={!!actionLoadingBtn}
                          className="rounded bg-danger/10 px-2 py-1 text-xs font-medium text-danger hover:bg-danger/20"
                        >
                          <X size={12} className="inline" /> Kapat
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {positions.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted" colSpan={10}>Açık pozisyon yok.</td>
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

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[1fr_1fr_1fr]">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Edge (İşlem Ekonomisi)</h2>
          {economics && economics.edge.trades > 0 ? (
            <div className="grid grid-cols-2 gap-4">
              <Metric label="Expectancy (R)" value={economics.edge.expectancy_r.toFixed(2)} />
              <Metric label="Beklenti / işlem" value={`$${money(economics.edge.expectancy)}`} />
              <Metric label="Kazanma oranı" value={`%${(economics.edge.win_rate * 100).toFixed(1)}`} />
              <Metric label="Başabaş oranı" value={`%${(economics.edge.break_even_win_rate * 100).toFixed(1)}`} />
              <Metric label="Payoff" value={economics.edge.payoff_ratio.toFixed(2)} />
              <Metric
                label="Edge"
                value={`${economics.edge.edge >= 0 ? "+" : ""}${(economics.edge.edge * 100).toFixed(1)}%`}
              />
              <div className="col-span-2">
                <span
                  className={`rounded px-2 py-1 text-xs font-semibold ${
                    economics.edge.has_edge ? "bg-primary/15 text-primary" : "bg-danger/15 text-danger"
                  }`}
                >
                  {economics.edge.has_edge ? "Pozitif edge (maliyet sonrası)" : "Edge yok / negatif"}
                </span>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted">Kapanmış işlem yok — edge için işlem birikmeli.</p>
          )}
        </Card>

        <Card>
          <h2 className="mb-4 text-base font-semibold">Maliyet Köprüsü</h2>
          {economics ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted">Brüt PnL</span>
                <span className="font-medium">${money(economics.cost_bridge.gross_pnl)}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted">− Ücretler</span>
                <span className="font-medium text-danger">−${money(economics.cost_bridge.total_fees)}</span>
              </div>
              <div className="flex items-center justify-between border-t border-border pt-3 text-sm">
                <span className="font-semibold">Net PnL</span>
                <span
                  className={
                    economics.cost_bridge.net_pnl >= 0 ? "font-semibold text-primary" : "font-semibold text-danger"
                  }
                >
                  ${money(economics.cost_bridge.net_pnl)}
                </span>
              </div>
              {economics.cost_bridge.gross_pnl > 0 ? (
                <p className="text-xs text-muted">
                  Ücretler brüt PnL&apos;in %{(economics.cost_bridge.fee_pct_of_gross * 100).toFixed(1)}&apos;ini götürdü.
                </p>
              ) : (
                <p className="text-xs text-muted">
                  Toplam ücret ${money(economics.cost_bridge.total_fees)} (brüt PnL ≤ 0).
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted">Veri yok.</p>
          )}
        </Card>

        <Card>
          <div className="mb-4 flex items-center gap-2">
            <PieChart size={17} />
            <h2 className="text-base font-semibold">Çıkış Tipleri</h2>
          </div>
          {exitPieData.length > 0 ? (
            <div className="h-52">
              <ResponsiveContainer width="100%" height="100%">
                <RePieChart>
                  <Pie data={exitPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, value }) => `${name}: ${value}`}>
                    {exitPieData.map((entry) => (
                      <Cell key={entry.name} fill={EXIT_COLORS[entry.name] || "#94a3b8"} />
                    ))}
                  </Pie>
                  <Tooltip />
                </RePieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-sm text-muted">Kapanmış işlem yok.</p>
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
              {fmtUTC(diagnostics.last_evaluation_at, true)}
            </p>
          )}
          {diagnostics && Object.keys(diagnostics.reason_counts).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(diagnostics.reason_counts).map(([reason, count]) => {
                const pct = (count / maxReasonCount) * 100;
                const approved = reason.startsWith("approved") || reason.startsWith("long_entry") || reason.startsWith("short_entry");
                return (
                  <div key={reason}>
                    <div className="flex items-center justify-between text-sm">
                      <span className={approved ? "font-medium text-primary" : ""}>{reason}</span>
                      <span className="text-muted">{count}</span>
                    </div>
                    <div className="mt-1 h-1.5 w-full rounded bg-border">
                      <div
                        className={`h-1.5 rounded ${approved ? "bg-primary" : "bg-amber-600"}`}
                        style={{ width: `${Math.round(pct)}%` }}
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
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2" scope="col">Sembol</th>
                  <th scope="col">Son Neden</th>
                  <th scope="col">Zaman</th>
                </tr>
              </thead>
              <tbody>
                {diagnostics && Object.keys(diagnostics.latest_by_symbol).length > 0 ? (
                  Object.entries(diagnostics.latest_by_symbol).map(([symbol, info]) => (
                    <tr key={symbol} className="border-b border-border">
                      <td className="py-3 font-medium">{symbol}</td>
                      <td className={info.reason.includes("entry") || info.reason === "approved" ? "text-primary font-medium" : "text-muted"}>
                        {info.reason}
                      </td>
                      <td className="text-xs text-muted">{info.at ? fmtUTC(info.at, true) : "-"}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td className="py-6 text-muted" colSpan={3}>Kayıt yok.</td>
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
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2" scope="col">Zaman</th>
                  <th scope="col">Sembol</th>
                  <th scope="col">Yön</th>
                  <th scope="col">Fiyat</th>
                  <th scope="col">Miktar</th>
                  <th scope="col">Ücret</th>
                  <th scope="col">PnL</th>
                  <th scope="col">Çıkış</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((trade) => {
                  const pnl = Number(trade.realized_pnl);
                  return (
                    <tr key={trade.id} className="border-b border-border">
                      <td className="py-3 text-muted">
                        {fmtUTC(trade.traded_at)}
                      </td>
                      <td className="font-medium">{trade.symbol}</td>
                      <td>
                        <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold uppercase text-white ${trade.side === "buy" ? "bg-primary" : "bg-danger"}`}>
                          {trade.side === "buy" ? "AL" : "SAT"}
                        </span>
                      </td>
                      <td>${fmtPrice(trade.price)}</td>
                      <td>{fmtQty(trade.quantity)}</td>
                      <td className="text-muted">${fmtPrice(trade.fee)}</td>
                      <td className={pnl >= 0 ? "font-medium text-primary" : "font-medium text-danger"}>
                        ${money(trade.realized_pnl)}
                      </td>
                      <td className="text-xs text-muted">
                        {trade.exit_reason ? trade.exit_reason.replace(/_/g, " ") : "giriş"}
                      </td>
                    </tr>
                  );
                })}
                {trades.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted" colSpan={8}>İşlem geçmişi yok.</td>
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
        message="Bot durdurulacak ve tüm paper trading verileri (işlemler, pozisyonlar, equity) silinecek. Emin misiniz?"
        confirmLabel="Sıfırla"
        danger
        onConfirm={async () => {
          await action(() => resetPaperTrading(), "Sıfırlandı", "reset");
          setConfirmReset(false);
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
