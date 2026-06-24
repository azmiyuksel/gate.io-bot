"use client";

import {
  Activity,
  BarChart3,
  PieChart,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  Trophy,
} from "lucide-react";
import {
  Cell,
  PieChart as RePieChart,
  Pie,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import LivePrices from "@/components/live-prices";
import { Card } from "@/components/ui/card";
import { Metric } from "@/components/ui/metric";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { LastUpdated } from "@/components/ui/last-updated";
import { useToast } from "@/components/ui/toast";
import { getAccessToken } from "@/lib/auth-api";
import { fmtUTCShort, money } from "@/lib/utils";
import type { PaperStream } from "@/lib/paper-api";
import {
  createPaperStream,
  getPaperEconomics,
  getPaperEquity,
  getPaperExitStats,
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
  PaperEconomics,
  PaperEquityPoint,
  PaperPosition,
  PaperRiskStatus,
  PaperSignalDiagnostics,
  PaperStatus,
  PaperTrade,
} from "@/types/paper";

import {
  EquityChart,
  ErrorBoundary,
  OrdersTradesTable,
  PaperControls,
  PositionsTable,
  QuickTrade,
  RiskDisplay,
  SignalDiagnostics,
} from "./_components";

const EXIT_COLORS: Record<string, string> = {
  stop_loss: "#b42318",
  trailing_stop: "#d97706",
  take_profit: "#146c5d",
  scale_out: "#0d9488",
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

  const [quickSymbol, setQuickSymbol] = useState("BTC_USDT");
  const [quickSide, setQuickSide] = useState<"buy" | "sell">("buy");
  const [quickQty, setQuickQty] = useState("0.01");
  const [connectionError, setConnectionError] = useState(false);
  const [streamConnected, setStreamConnected] = useState(false);

  const sseRef = useRef<PaperStream | null>(null);
  const botStatusRef = useRef("STOPPED");
  const actionRef = useRef<
    (fn: () => Promise<boolean>, successMsg: string, btnId?: string) => Promise<void>
  >(async () => {});

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  // Status (equity, metrics, exposure) arrives via the SSE stream, so it is NOT
  // re-fetched here — polling it too would double the heavy metrics computation on
  // the shared DB. The fast loop only covers data the stream does not push.
  const fetchFast = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    setConnectionError(false);
    try {
      const [p, t, r] = await Promise.all([
        getPaperPositions().catch(() => []),
        getPaperTrades().catch(() => []),
        getPaperRiskStatus().catch(() => null),
      ]);
      setPositions(p);
      setTrades(t);
      if (r) setRisk(r);
      setLastUpdated(new Date());
    } catch {
      setConnectionError(true);
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

  useEffect(() => {
    if (!token) return;
    // One-shot status fetch for an instant first paint; live updates then come
    // from the SSE stream below (no recurring status poll).
    getPaperStatus().then((s) => {
      if (s) {
        setStatus(s);
        setLastUpdated(new Date());
      }
    });
    fetchFast();
    fetchSlow();
    sseRef.current = createPaperStream(
      (data) => {
        if (data) {
          setStreamConnected(true);
          setStatus(data);
          setLastUpdated(new Date());
        }
      },
      () => {
        // SSE connection was closed (reconnect failed or server dropped).
        setStreamConnected(false);
        setConnectionError(true);
      },
    );

    // Mutable refs for interval IDs so the visibility handler can clear
    // and re-create them without needing to re-run the entire effect.
    const intervals = {
      fast: setInterval(fetchFast, 5000) as unknown as number,
      slow: setInterval(fetchSlow, 30000) as unknown as number,
    };

    // Pause polling when the tab is hidden to save battery and backend load.
    // Resume + refresh on visibility restore so data is current when the
    // user returns. SSE is left alone — it will reconnect on its own.
    const onVisibility = () => {
      if (document.hidden) {
        clearInterval(intervals.fast);
        clearInterval(intervals.slow);
      } else {
        intervals.fast = setInterval(fetchFast, 5000) as unknown as number;
        intervals.slow = setInterval(fetchSlow, 30000) as unknown as number;
        fetchFast();
        fetchSlow();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      if (sseRef.current) sseRef.current.close();
      clearInterval(intervals.fast);
      clearInterval(intervals.slow);
    };
  }, [token, fetchFast, fetchSlow]);

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
    fetchFast();
    // Control actions (start/stop/pause/resume) change status — refresh it once
    // immediately rather than waiting for the next SSE tick.
    getPaperStatus().then((s) => s && setStatus(s));
  }

  useEffect(() => {
    actionRef.current = action;
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement
      )
        return;
      const s = e.key.toLowerCase();
      const st = botStatusRef.current;
      const act = actionRef.current;
      if (s === "s" && st === "STOPPED") act(() => startPaperTrading(), "Başlatıldı", "start");
      if (s === "p" && st === "RUNNING") act(() => pausePaperTrading(), "Duraklatıldı", "pause");
      if (s === "r" && st === "PAUSED") act(() => resumePaperTrading(), "Devam ediliyor", "resume");
      if (s === "x" && st !== "STOPPED") act(() => stopPaperTrading(), "Durduruldu", "stop");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const botStatus = status?.status ?? "STOPPED";
  botStatusRef.current = botStatus;

  const initialBalance = Number(status?.initial_balance ?? 0);
  const totalReturnPct =
    initialBalance > 0 ? ((Number(status?.equity ?? 0) - initialBalance) / initialBalance) * 100 : 0;

  const equityChartData = useMemo(
    () => equity.map((p) => ({ time: fmtUTCShort(p.timestamp), equity: p.equity, drawdown: p.drawdown })),
    [equity],
  );

  const dailyPnlData = useMemo(() => {
    const dailyMap = trades.reduce((acc, t) => {
      const key = new Date(t.traded_at).toISOString().slice(0, 10);
      acc[key] = (acc[key] || 0) + Number(t.realized_pnl);
      return acc;
    }, {} as Record<string, number>);
    return Object.entries(dailyMap)
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
  }, [trades]);

  const maxReasonCount = useMemo(
    () => (diagnostics ? Math.max(1, ...Object.values(diagnostics.reason_counts)) : 1),
    [diagnostics],
  );

  const EXIT_LABELS: Record<string, string> = {
    stop_loss: "Stop Loss",
    trailing_stop: "Trailing Stop",
    take_profit: "Take Profit",
    scale_out: "Scale Out",
    manual_close: "Manual Close",
    signal_sell: "Signal Sell",
    signal_cover: "Signal Cover",
    manual_partial: "Manual Partial",
  };

  const exitPieData = useMemo(
    () => exitStats
      ? Object.entries(exitStats).map(([reason, count]) => ({
          name: EXIT_LABELS[reason] ?? reason,
          key: reason, // original key for color lookup
          value: count,
        }))
      : [],
    [exitStats],
  );

  const shortcuts = [
    { key: "S", label: "Başlat", when: "STOPPED" },
    { key: "P", label: "Duraklat", when: "RUNNING" },
    { key: "R", label: "Devam Et", when: "PAUSED" },
    { key: "X", label: "Durdur", when: "RUNNING/PAUSED" },
  ];

  return (
    <ErrorBoundary>
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
          <PaperControls
            botStatus={botStatus}
            actionLoadingBtn={actionLoadingBtn}
            onAction={action}
            onResetClick={() => setConfirmReset(true)}
            shortcuts={shortcuts}
          />
        )}
      </header>

      {!lastUpdated && (
        <div className="mx-auto max-w-7xl px-6 pt-4">
          <div className="flex items-center gap-2 text-sm text-muted">
            <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-muted border-t-transparent" />
            İlk veriler yükleniyor…
          </div>
        </div>
      )}

      {connectionError && (
        <div className="mx-auto max-w-7xl px-6 pt-4">
          <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
            <strong>Bağlantı hatası</strong> — arka uç veya SSE akışıyla iletişim
            kurulamıyor. Veriler güncel olmayabilir. Sayfayı yenilemeyi deneyin.
            {!streamConnected && (
              <span className="ml-2 text-xs opacity-70">(stream bağlı değil)</span>
            )}
          </div>
        </div>
      )}

      {botStatus === "PAUSED" && !connectionError && (
        <div className="mx-auto max-w-7xl px-6 pt-4">
          <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            Bot bir risk limiti nedeniyle <strong>duraklatıldı</strong>
            {status?.pause_reason ? ` (${status.pause_reason})` : ""} — bu yüzden ilk
            alımdan sonra yeni işlem açılmıyor. Devam etmek için yukarıdaki{" "}
            <strong>Devam Et</strong> butonunu kullanın.
          </div>
        </div>
      )}

      {botStatus === "RUNNING" && (
        <div className="mx-auto max-w-7xl px-6 pt-4">
          <div className="rounded border border-blue-200 bg-blue-50 p-2 text-xs text-blue-700">
            <strong>Paper mod:</strong> Gerçek OHLC mum verileriyle değerlendirme. Strateji live ile aynı parametrelerde çalışır. Long + short sinyal üretir.
          </div>
        </div>
      )}

      {lastUpdated ? (
        <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
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
            label="Unrealized PnL"
            value={`$${money(status?.unrealized_pnl ?? 0)}`}
            icon={Number(status?.unrealized_pnl ?? 0) >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
          />
          <Metric
            label="Win Rate (son 100)"
            value={`${((status?.metrics?.win_rate_rolling_100 ?? 0) * 100).toFixed(1)}%`}
            icon={<Trophy size={18} />}
          />
          <Metric
            label="Rolling Sharpe"
            value={`${(status?.metrics?.rolling_sharpe ?? 0).toFixed(2)}`}
            icon={<BarChart3 size={18} />}
          />
          <Metric
            label="Max Drawdown"
            value={`${(Math.abs(status?.metrics?.drawdown ?? 0) * 100).toFixed(2)}%`}
            icon={<ShieldAlert size={18} />}
          />
        </section>
      ) : (
        <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          {[0, 1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="rounded-lg border border-border p-4">
              <div className="mb-3 h-3.5 w-20 animate-pulse rounded bg-border/70" />
              <div className="h-6 w-24 animate-pulse rounded bg-border/70" />
            </div>
          ))}
        </section>
      )}

      <section className="mx-auto max-w-7xl px-6 pb-6">
        <LivePrices />
      </section>

      {botStatus === "RUNNING" && (
        <section className="mx-auto max-w-7xl px-6 pb-6">
          <QuickTrade
            symbol={quickSymbol}
            side={quickSide}
            qty={quickQty}
            onSymbolChange={setQuickSymbol}
            onSideChange={setQuickSide}
            onQtyChange={setQuickQty}
            actionLoadingBtn={actionLoadingBtn}
            onAction={action}
            toast={toast}
          />
        </section>
      )}

      <EquityChart
        equityChartData={equityChartData}
        dailyPnlData={dailyPnlData}
        rollingSharpe={status?.metrics?.rolling_sharpe ?? 0}
      />

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        <PositionsTable
          positions={positions}
          actionLoadingBtn={actionLoadingBtn}
          onAction={action}
        />
        <RiskDisplay risk={risk} />
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
                      <Cell key={entry.key} fill={EXIT_COLORS[entry.key] || "#94a3b8"} />
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

      <SignalDiagnostics diagnostics={diagnostics} maxReasonCount={maxReasonCount} />

      <section className="mx-auto max-w-7xl px-6 pb-10">
        <OrdersTradesTable trades={trades} />
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
    </ErrorBoundary>
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
