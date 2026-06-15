"use client";

import {
  Brain,
  CheckCircle2,
  GitBranch,
  Lightbulb,
  Play,
  RefreshCw,
  Rocket,
  ShieldCheck,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { LastUpdated } from "@/components/ui/last-updated";
import { Metric } from "@/components/ui/metric";
import { PageSkeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { getAccessToken } from "@/lib/auth-api";
import { num } from "@/lib/utils";
import {
  approvePromotion,
  getDiscoveredFeatures,
  getKnowledge,
  getLearningStatus,
  getPromotionRequests,
  getRankings,
  rejectPromotion,
  startLearning,
} from "@/lib/learning-api";
import type {
  DiscoveredFeature,
  KnowledgeEntry,
  LearningStatus,
  PromotionRequest,
  StrategyRanking,
} from "@/types/learning";

const KNOW_COLORS: Record<string, string> = {
  PATTERN: "#0f766e",
  FAILURE: "#b42318",
  REGIME: "#7c3aed",
  PORTFOLIO: "#2563eb",
  FEATURE: "#146c5d",
  META: "#d97706",
};

export default function LearningPage() {
  const { toast } = useToast();
  const [token, setToken] = useState("");
  const [approver, setApprover] = useState("admin@example.com");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [status, setStatus] = useState<LearningStatus | null>(null);
  const [knowledge, setKnowledge] = useState<KnowledgeEntry[]>([]);
  const [features, setFeatures] = useState<DiscoveredFeature[]>([]);
  const [rankings, setRankings] = useState<StrategyRanking[]>([]);
  const [requests, setRequests] = useState<PromotionRequest[]>([]);

  const refresh = useCallback(async () => {
    if (!token) return;
    const [st, kb, f, r, pr] = await Promise.all([
      getLearningStatus(),
      getKnowledge(40),
      getDiscoveredFeatures(),
      getRankings(25),
      getPromotionRequests(),
    ]);
    setStatus(st);
    setKnowledge(kb);
    setFeatures(f);
    setRankings(r);
    setRequests(pr);
    setLastUpdated(new Date());
  }, [token]);

  useEffect(() => {
    setToken(getAccessToken());
  }, []);

  useEffect(() => {
    if (token) refresh();
  }, [token, refresh]);

  const onStart = useCallback(async () => {
    if (!token) return;
    setBusy(true);
    setMessage("");
    try {
      const res = await startLearning().catch(() => null);
      if (res) {
        setMessage(
          `Öğrenme turu #${res.cycle_id}: ${res.strategies_validated} doğrulandı, ` +
            `${res.promotion_requests} terfi talebi (insan onayı bekliyor). ` +
            `Güvenlik korundu: ${res.safety_invariants_held ? "EVET" : "HAYIR"}`
        );
        toast("Öğrenme turu başarıyla başlatıldı", "success");
        await refresh();
      } else {
        setMessage("Öğrenme turu başarısız (yetki/veri).");
        toast("Öğrenme turu başarısız", "error");
      }
    } finally {
      setBusy(false);
    }
  }, [token, refresh, toast]);

  const onApprove = useCallback(
    async (strategyId: number) => {
      if (!token) return;
      const res = await approvePromotion(strategyId, approver, "approved via dashboard");
      if (res) {
        setMessage(`Strateji #${strategyId} ONAYLANDI (production'a alındı, canlı trading değişmedi).`);
        toast(`Strateji #${strategyId} onaylandı`, "success");
        await refresh();
      }
    },
    [token, approver, refresh, toast]
  );

  const onReject = useCallback(
    async (requestId: number) => {
      if (!token) return;
      const res = await rejectPromotion(requestId, approver, "rejected via dashboard");
      if (res) {
        setMessage(`Talep #${requestId} reddedildi.`);
        toast(`Talep #${requestId} reddedildi`, "info");
        await refresh();
      }
    },
    [token, approver, refresh, toast]
  );

  const pending = requests.filter((r) => r.status === "AWAITING_APPROVAL");

  return (
    <main className="mx-auto max-w-7xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Brain className="h-7 w-7 text-teal-700" />
          <div>
            <Breadcrumb items={[{ label: "Otomatik Öğrenme" }]} />
            <h1 className="text-2xl font-semibold">Otomatik Öğrenme & Sürekli Evrim</h1>
            <p className="text-sm text-neutral-500">
              Araştırma → Doğrulama → Paper → <strong>İnsan Onayı</strong> → Production
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <LastUpdated time={lastUpdated} onRefresh={refresh} loading={busy} />
          <Input className="w-52" placeholder="Onaylayan e-posta" value={approver} onChange={(e) => setApprover(e.target.value)} />
          <Button onClick={refresh}>
            <RefreshCw className="mr-1 h-4 w-4" /> Yenile
          </Button>
          <Button onClick={onStart} disabled={busy}>
            <Play className={`mr-1 h-4 w-4 ${busy ? "animate-pulse" : ""}`} /> Öğrenme Turu
          </Button>
        </div>
      </header>

      <div className="flex items-center gap-2 rounded-md bg-amber-50 px-4 py-2 text-sm text-amber-800">
        <ShieldCheck className="h-4 w-4" />
        Bu sistem tam otonom değildir: hiçbir strateji insan onayı olmadan canlıya geçmez; risk
        limitleri ve kill-switch'e dokunmaz.
      </div>

      {message && <div className="rounded-md bg-teal-50 px-4 py-2 text-sm text-teal-800">{message}</div>}

      {status === null ? (
        <PageSkeleton />
      ) : (
        <>
          {status && (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-4">
          <Card className="p-5">
            <div className="flex items-center gap-2 text-sm text-neutral-500">
              <Sparkles className="h-4 w-4" /> Onay Bekleyen
            </div>
            <div className="mt-1 text-3xl font-bold text-amber-600">{status.pending_approvals}</div>
          </Card>
          <Card className="p-5">
            <div className="flex items-center gap-2 text-sm text-neutral-500">
              <GitBranch className="h-4 w-4" /> Son Tur
            </div>
            <div className="mt-1 text-lg font-semibold">
              {status.latest_cycle ? `#${status.latest_cycle.id} · ${status.latest_cycle.status}` : "—"}
            </div>
          </Card>
          <Card className="p-5">
            <div className="text-sm text-neutral-500">Knowledge Base</div>
            <div className="mt-1 text-3xl font-bold">{status.knowledge?.knowledge_entries ?? 0}</div>
            <div className="text-xs text-neutral-400">{status.knowledge?.strategy_versions ?? 0} strateji versiyonu</div>
          </Card>
          <Card className="p-5">
            <div className="text-sm text-neutral-500">Güvenlik İlkeleri</div>
            <div className="mt-1 text-3xl font-bold text-emerald-700">{status.safety_invariants?.length ?? 0}</div>
            <div className="text-xs text-neutral-400">aktif kısıtlama</div>
          </Card>
        </section>
      )}

      <Card className="p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-neutral-700">
          <Rocket className="h-4 w-4" /> Terfi Adayları (İnsan Onayı Gerekli)
        </h2>
        <div className="overflow-x-auto">
          <table role="table" className="w-full text-left text-sm">
            <thead className="text-neutral-500">
              <tr className="border-b">
                <th scope="col" className="py-2 pr-3">Talep</th>
                <th scope="col" className="py-2 pr-3">Strateji</th>
                <th scope="col" className="py-2 pr-3">Skor</th>
                <th scope="col" className="py-2 pr-3">Sharpe</th>
                <th scope="col" className="py-2 pr-3">Tutarlılık</th>
                <th scope="col" className="py-2">Karar</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((r) => (
                <tr key={r.id} className="border-b last:border-0">
                  <td className="py-2 pr-3">#{r.id}</td>
                  <td className="py-2 pr-3">#{r.strategy_id}</td>
                  <td className="py-2 pr-3 font-semibold">{num(r.ranking_score).toFixed(1)}</td>
                  <td className="py-2 pr-3">{num((r.validation as { sharpe?: number })?.sharpe).toFixed(2)}</td>
                  <td className="py-2 pr-3">
                    {(num((r.validation as { consistency?: number })?.consistency) * 100).toFixed(0)}%
                  </td>
                  <td className="py-2">
                    <div className="flex gap-2">
                      <Button
                        onClick={() => onApprove(r.strategy_id)}
                        className="bg-emerald-700 hover:brightness-95"
                      >
                        <ThumbsUp className="h-3 w-3" /> Onayla
                      </Button>
                      <Button
                        onClick={() => onReject(r.id)}
                        variant="danger"
                      >
                        <ThumbsDown className="h-3 w-3" /> Reddet
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {pending.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-6 text-center text-neutral-400">
                    Onay bekleyen terfi talebi yok.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card className="p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-neutral-700">
            <CheckCircle2 className="h-4 w-4" /> Strateji Sıralaması (0-100)
          </h2>
          <div className="overflow-x-auto">
            <table role="table" className="w-full text-left text-sm">
              <thead className="text-neutral-500">
                <tr className="border-b">
                  <th scope="col" className="py-2 pr-3">Strateji</th>
                  <th scope="col" className="py-2 pr-3">Skor</th>
                  <th scope="col" className="py-2 pr-3">Robust.</th>
                  <th scope="col" className="py-2 pr-3">WF</th>
                  <th scope="col" className="py-2">Stab.</th>
                </tr>
              </thead>
              <tbody>
                {rankings.map((r) => (
                  <tr key={r.id} className="border-b last:border-0">
                    <td className="py-2 pr-3">#{r.strategy_id}</td>
                    <td className="py-2 pr-3 font-semibold">{num(r.score).toFixed(1)}</td>
                    <td className="py-2 pr-3">{num(r.robustness).toFixed(1)}</td>
                    <td className="py-2 pr-3">{num(r.walk_forward).toFixed(1)}</td>
                    <td className="py-2">{num(r.stability).toFixed(1)}</td>
                  </tr>
                ))}
                {rankings.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-neutral-400">
                      Henüz sıralama yok.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>

        <Card className="p-5">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-neutral-700">
            <Lightbulb className="h-4 w-4" /> Keşfedilen Feature'lar
          </h2>
          <div className="overflow-x-auto">
            <table role="table" className="w-full text-left text-sm">
              <thead className="text-neutral-500">
                <tr className="border-b">
                  <th scope="col" className="py-2 pr-3">Feature</th>
                  <th scope="col" className="py-2 pr-3">Formül</th>
                  <th scope="col" className="py-2 pr-3">Korelasyon</th>
                  <th scope="col" className="py-2">Stabilite</th>
                </tr>
              </thead>
              <tbody>
                {features.map((f) => (
                  <tr key={f.id} className="border-b last:border-0">
                    <td className="py-2 pr-3 font-medium">{f.name}</td>
                    <td className="py-2 pr-3 font-mono text-xs text-neutral-500">{f.formula}</td>
                    <td className="py-2 pr-3">{num(f.correlation_with_profit).toFixed(4)}</td>
                    <td className="py-2">{num(f.stability_score).toFixed(2)}</td>
                  </tr>
                ))}
                {features.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-6 text-center text-neutral-400">
                      Henüz keşfedilen feature yok.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </section>

      <Card className="p-5">
        <h2 className="mb-3 text-sm font-semibold text-neutral-700">Bilgi Tabanı (Öğrenilenler)</h2>
        <div className="space-y-2">
          {knowledge.map((k) => (
            <div key={k.id} className="flex items-start gap-3 border-b pb-2 last:border-0">
              <span
                className="mt-0.5 rounded px-2 py-0.5 text-xs font-semibold text-white"
                style={{ background: KNOW_COLORS[k.knowledge_type] ?? "#666" }}
              >
                {k.knowledge_type}
              </span>
              <div>
                <div className="text-sm font-medium">{k.title}</div>
                <div className="text-xs text-neutral-500">{k.description}</div>
              </div>
            </div>
          ))}
          {knowledge.length === 0 && (
            <div className="py-6 text-center text-neutral-400">Bilgi tabanı boş.</div>
          )}
        </div>
      </Card>
        </>
      )}
    </main>
  );
}
