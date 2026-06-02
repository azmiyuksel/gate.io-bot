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
import { money } from "@/lib/utils";
import { authFetch, getAccessToken, login, logout } from "@/lib/auth-api";
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
    max_capital_per_trade_pct: "0.01",
    daily_max_loss_pct: "0.02",
    weekly_max_loss_pct: "0.05",
    max_open_positions: 3,
    min_reward_risk: "2",
    atr_multiplier: "1.5",
    trailing_stop_pct: "0.01",
  },
};

const chartData = [
  { date: "Mon", equity: 10000, pnl: 24 },
  { date: "Tue", equity: 10034, pnl: 34 },
  { date: "Wed", equity: 10018, pnl: -16 },
  { date: "Thu", equity: 10052, pnl: 34 },
  { date: "Fri", equity: 10080, pnl: 28 },
];

export function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary>(fallback);
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [loading, setLoading] = useState(false);

  async function refresh() {
    if (!token) return;
    setLoading(true);
    try {
      const response = await authFetch(`/dashboard/summary`);
      if (response.ok) setSummary(await response.json());
      else if (response.status === 401) {
        setToken("");
        setAuthError("Oturum süresi doldu, tekrar giriş yapın.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function saveRisk() {
    await authFetch(`/dashboard/strategy`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(summary.strategy),
    });
    await refresh();
  }

  async function closePosition(id: number) {
    await authFetch(`/dashboard/positions/${id}/close`, { method: "POST" });
    await refresh();
  }

  async function handleLogin() {
    setAuthError("");
    try {
      const tokens = await login(email, password);
      setToken(tokens.access_token);
      setPassword("");
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : "Giriş başarısız");
    }
  }

  async function handleLogout() {
    await logout();
    setToken("");
    setSummary(fallback);
  }

  // Restore an existing session from storage on first mount.
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
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div>
            <h1 className="text-xl font-semibold">Gate.io Spot Capital Bot</h1>
            <p className="text-sm text-muted">Düşük riskli spot strateji kontrol paneli</p>
          </div>
          <div className="flex items-center gap-3">
            {token ? (
              <>
                <Button onClick={refresh} disabled={loading}>
                  <Activity size={16} /> Yenile
                </Button>
                <Button onClick={handleLogout}>
                  <Lock size={16} /> Çıkış
                </Button>
              </>
            ) : (
              <>
                <Input
                  className="w-48"
                  placeholder="E-posta"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
                <Input
                  className="w-48"
                  placeholder="Parola"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  onKeyDown={(event) => event.key === "Enter" && handleLogin()}
                />
                <Button onClick={handleLogin}>
                  <Lock size={16} /> Giriş
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      {authError && (
        <div className="mx-auto max-w-7xl px-6 pt-4">
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
            {authError}
          </div>
        </div>
      )}

      <section className="mx-auto grid max-w-7xl gap-5 px-6 py-6 lg:grid-cols-4">
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
            <span className="text-sm text-muted">Win rate 62% · Max DD -1.4%</span>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
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
              <BarChart data={chartData}>
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

      <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-10 lg:grid-cols-[2fr_1fr]">
        <Card>
          <h2 className="mb-4 text-base font-semibold">Açık Pozisyonlar</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted">
                <tr>
                  <th className="py-2">Sembol</th>
                  <th>Giriş</th>
                  <th>Miktar</th>
                  <th>Stop</th>
                  <th>Hedef</th>
                  <th />
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
                      <Button className="bg-danger px-3" onClick={() => closePosition(position.id)}>
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
    </main>
  );
}

function Metric({ label, value, icon }: { label: string; value: string; icon: React.ReactNode }) {
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between text-muted">
        <span className="text-sm">{label}</span>
        {icon}
      </div>
      <div className="text-2xl font-semibold">{value}</div>
    </Card>
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
