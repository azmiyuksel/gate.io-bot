import type {
  DiscoveredFeature,
  KnowledgeEntry,
  LearningHypothesis,
  LearningRunResult,
  LearningStatus,
  PromotionRequest,
  StrategyRanking,
} from "@/types/learning";
import { authFetch } from "@/lib/auth-api";

async function getJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await authFetch(path);
    if (res.ok) return (await res.json()) as T;
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`Error fetching ${path}:`, err);
  }
  return fallback;
}

export const getLearningStatus = () =>
  getJson<LearningStatus | null>("/learning/status", null);

export const getKnowledge = (limit = 50) =>
  getJson<KnowledgeEntry[]>(`/learning/knowledge?limit=${limit}`, []);

export const getDiscoveredFeatures = (symbol = "BTC_USDT", timeframe = "1h") =>
  getJson<DiscoveredFeature[]>(`/learning/features?symbol=${symbol}&timeframe=${timeframe}`, []);

export const getRankings = (limit = 25) =>
  getJson<StrategyRanking[]>(`/learning/rankings?limit=${limit}`, []);

export const getPromotionRequests = (status?: string) =>
  getJson<PromotionRequest[]>(
    `/learning/promotion-requests${status ? `?status=${status}` : ""}`,
    []
  );

export const getLearningHypotheses = (limit = 30) =>
  getJson<LearningHypothesis[]>(`/learning/hypotheses?limit=${limit}`, []);

export async function startLearning(
  symbol = "BTC_USDT",
  timeframe = "1h",
  population?: number
): Promise<LearningRunResult | null> {
  try {
    const res = await authFetch(`/learning/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, timeframe, population }),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error starting learning:", err);
  }
  return null;
}

export async function approvePromotion(
  strategyId: number,
  decidedBy: string,
  note?: string
): Promise<PromotionRequest | null> {
  try {
    const res = await authFetch(`/learning/promote-request/${strategyId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decided_by: decidedBy, note }),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error approving promotion:", err);
  }
  return null;
}

export async function rejectPromotion(
  requestId: number,
  decidedBy: string,
  note?: string
): Promise<PromotionRequest | null> {
  try {
    const res = await authFetch(`/learning/promotion-requests/${requestId}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decided_by: decidedBy, note }),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error rejecting promotion:", err);
  }
  return null;
}
