"use client";

import { Activity, Lock, PauseCircle, PlayCircle, ShieldCheck, XCircle } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Metric } from "@/components/ui/metric";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { LastUpdated } from "@/components/ui/last-updated";
import { useToast } from "@/components/ui/toast";
import { money } from "@/lib/utils";
import { authFetch, getAccessToken, login, logout, register } from "@/lib/auth-api";
import type { DashboardSummary } from "@/types/dashboard";

const fallback: DashboardSummary = {
  total_balance: "0",
  daily_pnl: "0",
  weekly_pnl: "0",
  bot_enabled: false,
  open_positions: [],
  recent_trades: [],
  strategy: {
    is_enabled: false,
    max_capital_per_trade_pct: "0.02",
    daily_max_loss_pct: "0.02",
    weekly_max_loss_pct: "0.05",
    max_open_positions: 5,
    min_reward_risk: "2",
    atr_multiplier: "1.5",
    trailing_stop_pct: "0.01",
  },
};

interface EquityPoint {
  date: string;
  equity: number;
}
interface PnlPoint {
  date: string;
  pnl: number;
}
interface ChartsData {
  equity_curve: EquityPoint[];
  daily_pnl: PnlPoint[];
  win_rate: number;
  max_drawdown: number;
}
interface EconomicsData {
  edge: {
    trades: number;
    expectancy: number;
    payoff_ratio: number;
    break_even_win_rate: number;
    edge: number;
    has_edge: boolean;
  };
  benchmark: {
    strategy_return: number;
    benchmark_return: number;
    excess_return: number;
    outperforms: boolean;
    benchmark_symbol: string;
  };
  hurdle: {
    annual_risk_free_rate: number;
    excess_over_hurdle: number;
    beats_hurdle: boolean;
  };
}

export function Dashboard() {
  const { toast } = useToast();
  const [summary, setSummary] = useState<DashboardSummary>(fallback);
  const [charts, setCharts] = useState<ChartsData>({
    equity_curve: [],
    daily_pnl: [],
    win_rate: 0,
    max_drawdown: 0,
  });
  const [economics, setEconomics] = useState<EconomicsData | null>(null);
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [confirmClose, setConfirmClose] = useState<{ id: number; symbol: string } | null>(null);

  async function refresh() {
    if (!token) return;
    setLoading(true);
    try {
      const response = await authFetch(`/dashboard/summary`);
      if (response.ok) {
        setSummary(await response.json());
        setLastUpdated(new Date());
      } else if (response.status === 401) {
        setToken("");
        setAuthError("Oturum süresi doldu, tekrar giriş yapın.");
        return;
      } else {
        toast("Dashboard verisi alınamadı", "error");
      }
      const chartsResponse = await authFetch(`/dashboard/charts`);
      if (chartsResponse.ok) setCharts(await chartsResponse.json());
      const econResponse = await authFetch(`/dashboard/economics`);
      if (econResponse.ok) setEconomics(await econResponse.json());
    } catch {
      toast("Sunucuya ulaşılamadı", "error");
    } finally {
      setLoading(false);
    }
  }

  async function saveRisk() {
    const res = await authFetch(`/dashboard/strategy`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(summary.strategy),
    });
    if (res.ok) {
      toast("Risk ayarları kaydedildi", "success");
      await refresh();
    } else {
      toast("Risk ayarları kaydedilemedi", "error");
    }
  }

  async function closePosition(id: number, _symbol: string) {
    const res = await authFetch(`/dashboard/positions/${id}/close`, { method: "POST" });
    if (res.ok) {
      toast("Pozisyon kapatıldı", "success");
      await refresh();
    } else {
      toast("Pozisyon kapatılamadı", "error");
    }
    setConfirmClose(null);
  }

  async function handleLogin() {
    setAuthError("");
    try {
      const tokens = await login(email, password);
      setToken(tokens.access_token);
      setPassword("");
      toast("Giriş başarılı", "success");
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Giriş başarısız");
    }
  }

  async function handleRegister() {
    setAuthError("");
    try {
      const tokens = await register(email, password);
      setToken(tokens.access_token);
      setPassword("");
      toast("Kayıt başarılı", "success");
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Kayıt başarısız");
    }
  }

  async function handleLogout() {
    await logout();
    setToken("");
    setSummary(fallback);
    toast("Çıkış yapıldı", "info");
  }

  useEffect(() => {
    const stored = getAccessToken();
    if (stored) setToken(stored);
  }, []);

  useEffect(() => {
    refresh();
  }, [token]);

  return (
    <main className="min-h-screen">
      <header className="border-b border-border bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold">Gate.io Spot Capital Bot</h1>
            <p className="text-sm text-muted">Düşük riskli spot strateji kontrol paneli</p>
          </div>
          <div className="flex items-center gap-3">
            {token ? (
              <>
                <LastUpdated time={lastUpdated} onRefresh={refresh} loading={loading} />
                <Button onClick={handleLogout}>
                  <Lock size={16} /> Çıkış
                </Button>
              </>
            ) : (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleLogin();
                }}
                className="flex items-center gap-3"
              >
                <Input
                  className="w-48"
                  placeholder="E-posta"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  aria-label="E-posta adresi"
                />
                <Input
                  className="w-48"
                  placeholder="Parola"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  aria-label="Parola"
                />
                <Button type="submit">
                  <Lock size={16} /> Giriş
                </Button>
                <Button type="button" onClick={handleRegister}>
                  Kayıt Ol
                </Button>
              </form>
            )}
          </div>
        </div>
      </header>

      {authError && (
        <div className="mx-auto max-w-7xl px-6 pt-4">
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700" role="alert">
            {authError}
          </div>
        </div>
      )}

      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Toplam bakiye" value={`$${money(summary.total_balance)}`} icon={<ShieldCheck size={18} />} />
        <Metric label="Günlük PnL" value={`$${money(summary.daily_pnl)}`} icon={<Activity size={18} />} />
        <Metric label="Haftalık PnL" value={`$${money(summary.weekly_pnl)}`} icon={<Activity size={18} />} />
        <Metric
          label="Bot durumu"
          value={summary.bot_enabled ? "Çalışıyor" : "Durdu"}
          icon={summary.bot_enabled ? <PlayCircle size={18} /> : <PauseCircle size={18} />}
        />
      </section>

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">Equity Curve</h2>
            <span className="text-sm text-muted">
              Win rate {charts.win_rate.toFixed(1)}% · Max DD {money(String(charts.max_drawdown))}
            </span>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={charts.equity_curve}>
                <CartesianGrid stroke="#ecece7" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Area type="monotone" dataKey="equity" stroke="#146c5d" fill="#146c5d33" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <h2 className="mb-4 text-base font-semibold">Günlük PnL</h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={charts.daily_pnl}>
                <CartesianGrid stroke="#ecece7" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="pnl" fill="#146c5d" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </section>

      {economics && economics.edge.trades > 0 && (
        <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label="İşlem başı beklenen değer (EV)"
            value={`$${economics.edge.expectancy.toFixed(2)}`}
            icon={<Activity size={18} />}
          />
          <Metric
            label={`Edge (win-rate − başabaş)`}
            value={`${(economics.edge.edge * 100).toFixed(1)}%`}
            icon={economics.edge.has_edge ? <ShieldCheck size={18} /> : <XCircle size={18} />}
          />
          <Metric
            label="Payoff oranı"
            value={`${economics.edge.payoff_ratio.toFixed(2)}x`}
            icon={<Activity size={18} />}
          />
          <Metric
            label={`Al-tut'a göre (${economics.benchmark.benchmark_symbol})`}
            value={`${(economics.benchmark.excess_return * 100).toFixed(1)}%`}
            icon={economics.benchmark.outperforms ? <ShieldCheck size={18} /> : <XCircle size={18} />}
          />
          <Metric
            label={`Risk-free hurdle üstü (%${(economics.hurdle.annual_risk_free_rate * 100).toFixed(0)}/yıl)`}
            value={`${(economics.hurdle.excess_over_hurdle * 100).toFixed(1)}%`}
            icon={economics.hurdle.beats_hurdle ? <ShieldCheck size={18} /> : <XCircle size={18} />}
          />
        </section>
      )}

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-10 lg:grid-cols-[2fr_1fr]">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Açık Pozisyonlar</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" role="table">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2" scope="col">Sembol</th>
                  <th scope="col">Giriş</th>
                  <th scope="col">Miktar</th>
                  <th scope="col">Stop</th>
                  <th scope="col">Hedef</th>
                  <th scope="col"><span className="sr-only">İşlem</span></th>
                </tr>
              </thead>
              <tbody>
                {summary.open_positions.map((position) => (
                  <tr key={position.id} className="border-b border-border">
                    <td className="py-3 font-medium">{position.symbol}</td>
                    <td>{money(position.entry_price)}</td>
                    <td>{money(position.quantity)}</td>
                    <td>{money(position.stop_loss)}</td>
                    <td>{money(position.take_profit)}</td>
                    <td className="text-right">
                      <Button
                        className="bg-danger px-3"
                        onClick={() => setConfirmClose({ id: position.id, symbol: position.symbol })}
                        aria-label={`${position.symbol} pozisyonunu kapat`}
                      >
                        <XCircle size={16} /> Kapat
                      </Button>
                    </td>
                  </tr>
                ))}
                {summary.open_positions.length === 0 && (
                  <tr>
                    <td className="py-6 text-muted" colSpan={6}>Açık pozisyon yok.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <div className="mb-4 flex items-center gap-2">
            <Lock size={17} />
            <h2 className="text-base font-semibold">Risk Ayarları</h2>
          </div>
          <RiskInput label="İşlem sermaye %" value={summary.strategy.max_capital_per_trade_pct} onChange={(value) => setSummary({ ...summary, strategy: { ...summary.strategy, max_capital_per_trade_pct: value } })} />
          <RiskInput label="Günlük zarar %" value={summary.strategy.daily_max_loss_pct} onChange={(value) => setSummary({ ...summary, strategy: { ...summary.strategy, daily_max_loss_pct: value } })} />
          <RiskInput label="Haftalık zarar %" value={summary.strategy.weekly_max_loss_pct} onChange={(value) => setSummary({ ...summary, strategy: { ...summary.strategy, weekly_max_loss_pct: value } })} />
          <RiskInput label="ATR çarpanı" value={summary.strategy.atr_multiplier} onChange={(value) => setSummary({ ...summary, strategy: { ...summary.strategy, atr_multiplier: value } })} />
          <Button className="mt-4 w-full" onClick={saveRisk}>Kaydet</Button>
        </Card>
      </section>

      <ConfirmDialog
        open={!!confirmClose}
        title="Pozisyonu Kapat"
        message={`${confirmClose?.symbol} pozisyonunu kapatmak istediğinize emin misiniz? Bu işlem geri alınamaz.`}
        confirmLabel="Kapat"
        danger
        onConfirm={() => confirmClose && closePosition(confirmClose.id, confirmClose.symbol)}
        onCancel={() => setConfirmClose(null)}
      />
    </main>
  );
}

function RiskInput({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="mb-3 block text-sm">
      <span className="mb-1 block text-muted">{label}</span>
      <Input value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
