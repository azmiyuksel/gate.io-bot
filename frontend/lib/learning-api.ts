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

async function getJson<T>(token: string, path: string, fallback: T): Promise<T> {
  try {
    const res = await authFetch(path);
    if (res.ok) return (await res.json()) as T;
  } catch (err) {
    console.error(`Error fetching ${path}:`, err);
  }
  return fallback;
}

export const getLearningStatus = (token: string) =>
  getJson<LearningStatus | null>(token, "/learning/status", null);

export const getKnowledge = (token: string, limit = 50) =>
  getJson<KnowledgeEntry[]>(token, `/learning/knowledge?limit=${limit}`, []);

export const getDiscoveredFeatures = (token: string, symbol = "BTC_USDT", timeframe = "1h") =>
  getJson<DiscoveredFeature[]>(token, `/learning/features?symbol=${symbol}&timeframe=${timeframe}`, []);

export const getRankings = (token: string, limit = 25) =>
  getJson<StrategyRanking[]>(token, `/learning/rankings?limit=${limit}`, []);

export const getPromotionRequests = (token: string, status?: string) =>
  getJson<PromotionRequest[]>(
    token,
    `/learning/promotion-requests${status ? `?status=${status}` : ""}`,
    []
  );

export const getLearningHypotheses = (token: string, limit = 30) =>
  getJson<LearningHypothesis[]>(token, `/learning/hypotheses?limit=${limit}`, []);

export async function startLearning(
  token: string,
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
    console.error("Error starting learning:", err);
  }
  return null;
}

export async function approvePromotion(
  token: string,
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
    console.error("Error approving promotion:", err);
  }
  return null;
}

export async function rejectPromotion(
  token: string,
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
    console.error("Error rejecting promotion:", err);
  }
  return null;
}
