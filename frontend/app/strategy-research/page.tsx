"use client";

import {
  Beaker,
  CheckCircle2,
  FlaskConical,
  Lightbulb,
  Play,
  RefreshCw,
  Rocket,
  Trophy,
  XCircle,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useCallback, useEffect, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LastUpdated } from "@/components/ui/last-updated";
import { Metric } from "@/components/ui/metric";
import { useToast } from "@/components/ui/toast";
import { getAccessToken } from "@/lib/auth-api";
import {
  getExperiments,
  getFeatures,
  getHypotheses,
  getLeaderboard,
  getStrategies,
  promoteStrategy,
  recomputeFeatures,
  runResearch,
  testHypotheses,
} from "@/lib/strategy-research-api";
import type {
  FeatureRecord,
  HypothesisTest,
  ResearchExperiment,
  ResearchStrategy,
  StrategyVersion,
} from "@/types/strategy-research";

const STATUS_COLORS: Record<string, string> = {
  PROMOTED: "#146c5d",
  CANDIDATE: "#0f766e",
  REJECTED: "#b42318",
  ARCHIVED: "#6b7280",
};

const HYP_COLORS: Record<string, string> = {
  SUPPORTED: "#146c5d",
  REJECTED: "#b42318",
  INCONCLUSIVE: "#d97706",
  UNTESTED: "#6b7280",
};

function num(v: string | number | null | undefined): number {
  if (v === null || v === undefined) return 0;
  return typeof v === "number" ? v : Number(v);
}

export default function StrategyResearchPage() {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [symbol, setSymbol] = useState("BTC_USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [strategies, setStrategies] = useState<ResearchStrategy[]>([]);
  const [leaderboard, setLeaderboard] = useState<StrategyVersion[]>([]);
  const [features, setFeatures] = useState<FeatureRecord[]>([]);
  const [hypotheses, setHypotheses] = useState<HypothesisTest[]>([]);
  const [experiments, setExperiments] = useState<ResearchExperiment[]>([]);

  const refresh = useCallback(async () => {
    if (!token) return;
    const [s, lb, f, h, e] = await Promise.all([
      getStrategies(),
      getLeaderboard(25),
      getFeatures(symbol, timeframe),
      getHypotheses(20),
      getExperiments(30),
    ]);
    setStrategies(s);
    setLeaderboard(lb);
    setFeatures(f);
    setHypotheses(h);
    setExperiments(e);
    setLastUpdated(new Date());
  }, [token, symbol, timeframe]);

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  useEffect(() => {
    if (token) refresh();
  }, [token, refresh]);

  const onRun = useCallback(async () => {
    if (!token) return;
    setBusy("run");
    setMessage("");
    try {
      const result = await runResearch(symbol, timeframe);
      if (result) {
        const msg = result.evaluated
          ? `Tur tamamlandı: ${result.evaluated} strateji denendi, ${result.promoted} terfi, en iyi fitness ${result.best_fitness}`
          : `Yetersiz veri: ${result.reason ?? "historical candle yok"}`;
        setMessage(msg);
        toast(msg, "success");
        await refresh();
      } else {
        setMessage("Araştırma turu başarısız (yetki/sembol).");
        toast("Araştırma turu başarısız (yetki/sembol).", "error");
      }
    } finally {
      setBusy("");
    }
  }, [token, symbol, timeframe, refresh, toast]);

  const onRecomputeFeatures = useCallback(async () => {
    if (!token) return;
    setBusy("features");
    try {
      const f = await recomputeFeatures(symbol, timeframe);
      setFeatures(f);
      const msg = `${f.length} feature yeniden hesaplandı.`;
      setMessage(msg);
      toast(msg, "success");
    } finally {
      setBusy("");
    }
  }, [token, symbol, timeframe, toast]);

  const onTestHypotheses = useCallback(async () => {
    if (!token) return;
    setBusy("hypotheses");
    try {
      const h = await testHypotheses(symbol, timeframe);
      setHypotheses(h);
      const msg = `${h.length} hipotez test edildi.`;
      setMessage(msg);
      toast(msg, "success");
    } finally {
      setBusy("");
    }
  }, [token, symbol, timeframe, toast]);

  const onPromote = useCallback(
    async (strategyId: number) => {
      if (!token) return;
      const result = await promoteStrategy(strategyId);
      if (result) {
        const msg = `Strateji #${strategyId}: ${result.decision} — ${result.reasons.join("; ")}`;
        setMessage(msg);
        toast(msg, "success");
        await refresh();
      } else {
        toast("Terfi işlemi başarısız.", "error");
      }
    },
    [token, refresh, toast]
  );

  const counts = strategies.reduce<Record<string, number>>((acc, s) => {
    acc[s.status] = (acc[s.status] ?? 0) + 1;
    return acc;
  }, {});

  const featureBars = features
    .slice(0, 12)
    .map((f) => ({ name: f.name, importance: num(f.importance_score), category: f.category }));

  const strategyName = (id: number | null) =>
    strategies.find((s) => s.id === id)?.name ?? (id ? `#${id}` : "—");

  return (
    <main className="mx-auto max-w-7xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Breadcrumb items={[{ label: "Araştırma Lab" }]} />
          <div className="mt-2 flex items-center gap-3">
            <FlaskConical className="h-7 w-7 text-teal-700" />
            <div>
              <h1 className="text-2xl font-semibold">Strateji Araştırma Laboratuvarı</h1>
              <p className="text-sm text-neutral-500">
                Strateji üretimi, evrimsel optimizasyon, A/B test ve production terfisi
              </p>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <LastUpdated time={lastUpdated} onRefresh={refresh} loading={!!busy} />
          <Input className="w-36" placeholder="Sembol" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} />
          <Input className="w-20" placeholder="TF" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} />
          <Button onClick={refresh}>
            <RefreshCw className="mr-1 h-4 w-4" /> Yenile
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap gap-2">
        <Button onClick={onRun} disabled={busy === "run"}>
          <Play className={`mr-1 h-4 w-4 ${busy === "run" ? "animate-pulse" : ""}`} /> Araştırma Turu Çalıştır
        </Button>
        <Button onClick={onRecomputeFeatures} disabled={busy === "features"}>
          <Beaker className="mr-1 h-4 w-4" /> Feature'ları Hesapla
        </Button>
        <Button onClick={onTestHypotheses} disabled={busy === "hypotheses"}>
          <Lightbulb className="mr-1 h-4 w-4" /> Hipotezleri Test Et
        </Button>
      </div>

      {message && <div className="rounded-md bg-teal-50 px-4 py-2 text-sm text-teal-800">{message}</div>}

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {(["PROMOTED", "CANDIDATE", "REJECTED", "ARCHIVED"] as const).map((st) => (
          <Metric key={st} label={st} value={String(counts[st] ?? 0)} />
        ))}
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card className="p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-neutral-700">
            <Trophy className="h-4 w-4" /> Strateji Lider Tablosu (fitness)
          </h2>
          <div className="overflow-x-auto">
            <table role="table" className="w-full text-left text-sm">
              <thead className="text-neutral-500">
                <tr className="border-b">
                  <th scope="col" className="py-2 pr-3">Strateji</th>
                  <th scope="col" className="py-2 pr-3">Fitness</th>
                  <th scope="col" className="py-2 pr-3">Sharpe</th>
                  <th scope="col" className="py-2 pr-3">DD</th>
                  <th scope="col" className="py-2 pr-3">Stab.</th>
                  <th scope="col" className="py-2 pr-3">Overfit</th>
                  <th scope="col" className="py-2">Aksiyon</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((v) => (
                  <tr key={v.id} className="border-b last:border-0">
                    <td className="py-2 pr-3">{strategyName(v.strategy_id)}</td>
                    <td className="py-2 pr-3 font-semibold">{num(v.fitness).toFixed(3)}</td>
                    <td className="py-2 pr-3">{num(v.sharpe).toFixed(2)}</td>
                    <td className="py-2 pr-3">{(num(v.max_drawdown) * 100).toFixed(1)}%</td>
                    <td className="py-2 pr-3">{num(v.stability_score).toFixed(2)}</td>
                    <td className="py-2 pr-3">
                      {v.overfit ? (
                        <XCircle className="h-4 w-4 text-red-600" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      )}
                    </td>
                    <td className="py-2">
                      <button
                        onClick={() => onPromote(v.strategy_id)}
                        className="inline-flex items-center gap-1 rounded bg-teal-700 px-2 py-1 text-xs text-white hover:bg-teal-800"
                      >
                        <Rocket className="h-3 w-3" /> Terfi
                      </button>
                    </td>
                  </tr>
                ))}
                {leaderboard.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-neutral-400">
                      Henüz değerlendirilmiş strateji yok. "Araştırma Turu Çalıştır" deyin.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold text-neutral-700">Feature Önem Skorları</h2>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={featureBars} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis type="number" domain={[0, 1]} fontSize={12} />
              <YAxis type="category" dataKey="name" width={120} fontSize={10} />
              <Tooltip />
              <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                {featureBars.map((entry, i) => (
                  <Cell key={i} fill={entry.importance >= 0.5 ? "#146c5d" : "#0f766e99"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </section>

      <Card className="p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-neutral-700">
          <Lightbulb className="h-4 w-4" /> Hipotez Testleri
        </h2>
        <div className="overflow-x-auto">
          <table role="table" className="w-full text-left text-sm">
            <thead className="text-neutral-500">
              <tr className="border-b">
                <th scope="col" className="py-2 pr-3">Hipotez</th>
                <th scope="col" className="py-2 pr-3">Koşul</th>
                <th scope="col" className="py-2 pr-3">Edge</th>
                <th scope="col" className="py-2 pr-3">p-değeri</th>
                <th scope="col" className="py-2 pr-3">Örnek</th>
                <th scope="col" className="py-2">Durum</th>
              </tr>
            </thead>
            <tbody>
              {hypotheses.map((h) => (
                <tr key={h.id} className="border-b last:border-0">
                  <td className="py-2 pr-3">{h.statement}</td>
                  <td className="py-2 pr-3 font-mono text-xs text-neutral-500">{h.condition}</td>
                  <td className="py-2 pr-3">{(num(h.edge) * 100).toFixed(3)}%</td>
                  <td className="py-2 pr-3">{num(h.p_value).toFixed(3)}</td>
                  <td className="py-2 pr-3">{h.sample_size}</td>
                  <td className="py-2">
                    <span
                      className="rounded px-2 py-0.5 text-xs font-semibold text-white"
                      style={{ background: HYP_COLORS[h.status] ?? "#666" }}
                    >
                      {h.status}
                    </span>
                  </td>
                </tr>
              ))}
              {hypotheses.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-neutral-400">
                    Hipotez kaydı yok — "Hipotezleri Test Et" deyin.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="mb-3 text-sm font-semibold text-neutral-700">Son Deneyler</h2>
        <div className="overflow-x-auto">
          <table role="table" className="w-full text-left text-sm">
            <thead className="text-neutral-500">
              <tr className="border-b">
                <th scope="col" className="py-2 pr-3">Zaman</th>
                <th scope="col" className="py-2 pr-3">Tür</th>
                <th scope="col" className="py-2 pr-3">Strateji</th>
                <th scope="col" className="py-2 pr-3">Fitness</th>
                <th scope="col" className="py-2">Durum</th>
              </tr>
            </thead>
            <tbody>
              {experiments.map((e) => (
                <tr key={e.id} className="border-b last:border-0">
                  <td className="py-2 pr-3 whitespace-nowrap">
                    {new Date(e.created_at).toLocaleString("tr-TR")}
                  </td>
                  <td className="py-2 pr-3">{e.experiment_type}</td>
                  <td className="py-2 pr-3">{strategyName(e.strategy_id)}</td>
                  <td className="py-2 pr-3">{num(e.fitness).toFixed(3)}</td>
                  <td className="py-2 text-neutral-500">{e.status}</td>
                </tr>
              ))}
              {experiments.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-neutral-400">
                    Deney kaydı yok.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </main>
  );
}
