"use client";

import {
  Beaker,
  CheckCircle2,
  Download,
  FlaskConical,
  Lightbulb,
  Play,
  RefreshCw,
  Rocket,
  Search,
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
import { useCallback, useEffect, useRef, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { LastUpdated } from "@/components/ui/last-updated";
import { Metric } from "@/components/ui/metric";
import { Pagination, usePagination } from "@/components/ui/pagination";
import { useToast } from "@/components/ui/toast";
import StrategyDetailSheet from "@/components/strategy-detail-sheet";
import { getAccessToken } from "@/lib/auth-api";
import { num } from "@/lib/utils";
import {
  getABTests,
  getExperiments,
  getFeatures,
  getHypotheses,
  getLeaderboard,
  getResearchSymbols,
  getStrategies,
  promoteStrategy,
  recomputeFeatures,
  runResearch,
  testHypotheses,
} from "@/lib/strategy-research-api";
import type {
  ABTest,
  FeatureRecord,
  HypothesisTest,
  ResearchExperiment,
  ResearchStrategy,
  ResearchSymbol,
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

function downloadCSV(headers: string[], rows: string[][], filename: string) {
  const csv = [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function StrategyResearchPage() {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [symbol, setSymbol] = useState("BTC_USDT");
  const [timeframe, setTimeframe] = useState("1h");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [hideOverfit, setHideOverfit] = useState(true);
  const [symbols, setSymbols] = useState<ResearchSymbol[]>([]);
  const [showSymbols, setShowSymbols] = useState(false);

  const [strategies, setStrategies] = useState<ResearchStrategy[]>([]);
  const [leaderboard, setLeaderboard] = useState<StrategyVersion[]>([]);
  const [features, setFeatures] = useState<FeatureRecord[]>([]);
  const [hypotheses, setHypotheses] = useState<HypothesisTest[]>([]);
  const [experiments, setExperiments] = useState<ResearchExperiment[]>([]);
  const [abtests, setAbtests] = useState<ABTest[]>([]);

  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailName, setDetailName] = useState("");
  const [promoteTarget, setPromoteTarget] = useState<{ id: number; name: string } | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async () => {
    if (!token) return;
    const [s, lb, f, h, e, ab] = await Promise.all([
      getStrategies(),
      getLeaderboard(100),
      getFeatures(symbol, timeframe),
      getHypotheses(50),
      getExperiments(100),
      getABTests(30),
    ]);
    setStrategies(s);
    setLeaderboard(lb);
    setFeatures(f);
    setHypotheses(h);
    setExperiments(e);
    setAbtests(ab);
    setLastUpdated(new Date());
  }, [token, symbol, timeframe]);

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  useEffect(() => {
    if (token) {
      refresh();
      getResearchSymbols().then(setSymbols);
    }
  }, [token, refresh]);

  useEffect(() => {
    if (!token) return;
    intervalRef.current = setInterval(refresh, 30000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
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
    async (strategyId: number, name: string) => {
      if (!token) return;
      const result = await promoteStrategy(strategyId);
      if (result) {
        const msg = `${name}: ${result.decision} — ${result.reasons.join("; ")}`;
        setMessage(msg);
        toast(msg, result.passed ? "success" : "warning");
        await refresh();
      } else {
        toast("Terfi işlemi başarısız.", "error");
      }
    },
    [token, refresh, toast]
  );

  const onOpenDetail = (id: number, name: string) => {
    setDetailId(id);
    setDetailName(name);
  };

  const counts = strategies.reduce<Record<string, number>>((acc, s) => {
    acc[s.status] = (acc[s.status] ?? 0) + 1;
    return acc;
  }, {});

  const featureBars = features
    .slice(0, 12)
    .map((f) => ({ name: f.name, importance: num(f.importance_score), category: f.category }));

  const strategyName = (id: number | null) =>
    strategies.find((s) => s.id === id)?.name ?? (id ? `#${id}` : "—");

  const filteredLeaderboard = hideOverfit
    ? leaderboard.filter((v) => !v.overfit)
    : leaderboard;

  const {
    page: lbPage,
    setPage: setLbPage,
    totalPages: lbTotalPages,
    paginatedItems: paginatedLB,
  } = usePagination(filteredLeaderboard, 10);

  const {
    page: hyPage,
    setPage: setHyPage,
    totalPages: hyTotalPages,
    paginatedItems: paginatedHypotheses,
  } = usePagination(hypotheses, 10);

  const {
    page: exPage,
    setPage: setExPage,
    totalPages: exTotalPages,
    paginatedItems: paginatedExperiments,
  } = usePagination(experiments, 15);

  const exportLeaderboard = () => {
    const headers = ["Strateji", "Fitness", "Sharpe", "DD", "Stab.", "Overfit", "Template"];
    const rows = filteredLeaderboard.map((v) => [
      strategyName(v.strategy_id),
      num(v.fitness).toFixed(3),
      num(v.sharpe).toFixed(2),
      `${(num(v.max_drawdown) * 100).toFixed(1)}%`,
      num(v.stability_score).toFixed(2),
      v.overfit ? "EVET" : "Hayır",
      strategies.find((s) => s.id === v.strategy_id)?.template ?? "",
    ]);
    downloadCSV(headers, rows, `leaderboard-${symbol}-${timeframe}.csv`);
    toast("Lider tablosu CSV olarak indirildi.", "success");
  };

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
          <div className="relative">
            <Input
              className="w-36"
              placeholder="Sembol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              onFocus={() => setShowSymbols(true)}
              onBlur={() => setTimeout(() => setShowSymbols(false), 200)}
            />
            {showSymbols && symbols.length > 0 && (
              <div className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded border border-border bg-white shadow-lg">
                {symbols
                  .filter((s) => s.symbol.includes(symbol))
                  .slice(0, 20)
                  .map((s) => (
                    <button
                      key={s.symbol}
                      className="w-full px-3 py-1.5 text-left text-sm hover:bg-neutral-100"
                      onMouseDown={() => {
                        setSymbol(s.symbol);
                        setShowSymbols(false);
                      }}
                    >
                      {s.symbol}
                    </button>
                  ))}
              </div>
            )}
          </div>
          <Input className="w-20" placeholder="TF" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} />
          <Button onClick={refresh}>
            <RefreshCw className={`mr-1 h-4 w-4 ${busy ? "animate-spin" : ""}`} /> Yenile
          </Button>
        </div>
      </header>

      <div className="flex flex-wrap gap-2">
        <Button onClick={onRun} disabled={busy === "run"}>
          <Play className={`mr-1 h-4 w-4 ${busy === "run" ? "animate-pulse" : ""}`} /> Araştırma Turu Çalıştır
        </Button>
        <Button onClick={onRecomputeFeatures} disabled={busy === "features"}>
          <Beaker className={`mr-1 h-4 w-4 ${busy === "features" ? "animate-pulse" : ""}`} /> Feature'ları Hesapla
        </Button>
        <Button onClick={onTestHypotheses} disabled={busy === "hypotheses"}>
          <Lightbulb className={`mr-1 h-4 w-4 ${busy === "hypotheses" ? "animate-pulse" : ""}`} /> Hipotezleri Test Et
        </Button>
        {busy && (
          <span className="flex items-center gap-1 text-xs text-neutral-500">
            <RefreshCw className="h-3 w-3 animate-spin" />
            {busy === "run" ? "Stratejiler değerlendiriliyor..." : busy === "features" ? "Feature'lar hesaplanıyor..." : "Hipotezler test ediliyor..."}
          </span>
        )}
      </div>

      {message && <div className="rounded-md bg-teal-50 px-4 py-2 text-sm text-teal-800">{message}</div>}

      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {(["PROMOTED", "CANDIDATE", "REJECTED", "ARCHIVED"] as const).map((st) => (
          <Metric key={st} label={st} value={String(counts[st] ?? 0)} />
        ))}
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-neutral-700">
              <Trophy className="h-4 w-4" /> Strateji Lider Tablosu (fitness)
            </h2>
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1 text-xs text-neutral-500">
                <input
                  type="checkbox"
                  checked={hideOverfit}
                  onChange={(e) => setHideOverfit(e.target.checked)}
                  className="rounded"
                />
                Overfit gizle
              </label>
              <Button onClick={exportLeaderboard} variant="ghost">
                <Download className="h-3 w-3" /> CSV
              </Button>
            </div>
          </div>
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
                {paginatedLB.map((v) => {
                  const s = strategies.find((x) => x.id === v.strategy_id);
                  const isPromoted = s?.status === "PROMOTED";
                  const isRejected = s?.status === "REJECTED";
                  return (
                    <tr key={v.id} className="border-b last:border-0">
                      <td className="py-2 pr-3">
                        <button
                          onClick={() => onOpenDetail(v.strategy_id, strategyName(v.strategy_id))}
                          className="text-left hover:text-teal-700 hover:underline"
                        >
                          {strategyName(v.strategy_id)}
                        </button>
                        <span
                          className="ml-1 rounded px-1 py-0.5 text-[10px] font-semibold text-white"
                          style={{ background: STATUS_COLORS[s?.status ?? ""] ?? "#888" }}
                        >
                          {s?.status ?? "?"}
                        </span>
                      </td>
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
                        {!isPromoted && !isRejected ? (
                          <button
                            onClick={() => onOpenDetail(v.strategy_id, strategyName(v.strategy_id))}
                            className="mr-1 rounded px-2 py-1 text-xs text-teal-700 hover:bg-teal-50"
                          >
                            <Search className="inline h-3 w-3" /> Detay
                          </button>
                        ) : null}
                        {!isPromoted && (
                          <button
                            onClick={() =>
                              setPromoteTarget({ id: v.strategy_id, name: strategyName(v.strategy_id) })
                            }
                            className="inline-flex items-center gap-1 rounded bg-teal-700 px-2 py-1 text-xs text-white hover:bg-teal-800"
                          >
                            <Rocket className="h-3 w-3" /> Terfi
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {filteredLeaderboard.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-neutral-400">
                      Henüz değerlendirilmiş strateji yok. "Araştırma Turu Çalıştır" deyin.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {lbTotalPages > 1 && (
            <Pagination page={lbPage} totalPages={lbTotalPages} onPageChange={setLbPage} />
          )}
        </Card>

        <Card className="p-5">
          <h2 className="mb-3 text-sm font-semibold text-neutral-700">Feature Önem Skorları</h2>
          {featureBars.length > 0 ? (
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
          ) : (
            <div className="flex h-80 items-center justify-center text-sm text-neutral-400">
              Feature verisi yok — "Feature'ları Hesapla" deyin.
            </div>
          )}
        </Card>
      </section>

      {abtests.length > 0 && (
        <Card className="p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-neutral-700">
            <Trophy className="h-4 w-4" /> A/B Test Sonuçları
          </h2>
          <div className="overflow-x-auto">
            <table role="table" className="w-full text-left text-sm">
              <thead className="text-neutral-500">
                <tr className="border-b">
                  <th className="py-2 pr-3">A</th>
                  <th className="py-2 pr-3">B</th>
                  <th className="py-2 pr-3">Kazanan</th>
                  <th className="py-2 pr-3">A Fit.</th>
                  <th className="py-2 pr-3">B Fit.</th>
                  <th className="py-2 pr-3">p</th>
                  <th className="py-2">Detay</th>
                </tr>
              </thead>
              <tbody>
                {abtests.slice(0, 10).map((ab) => (
                  <tr key={ab.id} className="border-b last:border-0">
                    <td className="py-2 pr-3">{strategyName(ab.strategy_a_id)}</td>
                    <td className="py-2 pr-3">{strategyName(ab.strategy_b_id)}</td>
                    <td className="py-2 pr-3 font-semibold">{ab.winner}</td>
                    <td className="py-2 pr-3">{num(ab.a_fitness).toFixed(3)}</td>
                    <td className="py-2 pr-3">{num(ab.b_fitness).toFixed(3)}</td>
                    <td className="py-2 pr-3">{num(ab.p_value).toFixed(3)}</td>
                    <td className="py-2 text-xs text-neutral-500">{ab.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

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
              {paginatedHypotheses.map((h) => (
                <tr key={h.id} className="border-b last:border-0">
                  <td className="py-2 pr-3">{h.statement}</td>
                  <td className="py-2 pr-3 font-mono text-xs text-neutral-500">{h.condition}</td>
                  <td className="py-2 pr-3">{(num(h.edge) * 100).toFixed(3)}%</td>
                  <td className="py-2 pr-3">{num(h.p_value).toFixed(4)}</td>
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
        {hyTotalPages > 1 && (
          <Pagination page={hyPage} totalPages={hyTotalPages} onPageChange={setHyPage} />
        )}
      </Card>

      <Card className="p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-neutral-700">Son Deneyler</h2>
          <Button
            onClick={() => {
              const headers = ["Zaman", "Tür", "Strateji", "Fitness", "Durum"];
              const rows = experiments.map((e) => [
                new Date(e.created_at).toLocaleString("tr-TR"),
                e.experiment_type,
                strategyName(e.strategy_id),
                num(e.fitness).toFixed(3),
                e.status,
              ]);
              downloadCSV(headers, rows, `experiments-${symbol}-${timeframe}.csv`);
              toast("Deneyler CSV olarak indirildi.", "success");
            }}
            variant="ghost"
          >
            <Download className="h-3 w-3" /> CSV
          </Button>
        </div>
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
              {paginatedExperiments.map((e) => (
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
        {exTotalPages > 1 && (
          <Pagination page={exPage} totalPages={exTotalPages} onPageChange={setExPage} />
        )}
      </Card>

      <StrategyDetailSheet
        strategyId={detailId ?? 0}
        strategyName={detailName}
        open={detailId !== null}
        onClose={() => setDetailId(null)}
      />

      <ConfirmDialog
        open={promoteTarget !== null}
        title="Stratejiyi Terfi Ettir"
        message={`"${promoteTarget?.name}" stratejisi production'a terfi ettirilecek. Bu işlem production promotion gate koşullarını uygular. Emin misiniz?`}
        confirmLabel="Terfi Ettir"
        onConfirm={() => {
          if (promoteTarget) {
            onPromote(promoteTarget.id, promoteTarget.name);
          }
          setPromoteTarget(null);
        }}
        onCancel={() => setPromoteTarget(null)}
      />
    </main>
  );
}
