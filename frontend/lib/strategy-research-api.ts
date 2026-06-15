import type {
  ABTest,
  FeatureRecord,
  HypothesisTest,
  PromotionResult,
  ResearchExperiment,
  ResearchRunResult,
  ResearchStrategy,
  ResearchSymbol,
  StrategyDetail,
  StrategyVersion,
} from "@/types/strategy-research";
import { authFetch } from "@/lib/auth-api";

export async function getStrategies(status?: string): Promise<ResearchStrategy[]> {
  try {
    const qs = status ? `?status=${status}` : "";
    const res = await authFetch(`/research/strategies${qs}`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching strategies:", err);
  }
  return [];
}

export async function getLeaderboard(limit = 25): Promise<StrategyVersion[]> {
  try {
    const res = await authFetch(`/research/leaderboard?limit=${limit}`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching leaderboard:", err);
  }
  return [];
}

export async function getExperiments(limit = 100): Promise<ResearchExperiment[]> {
  try {
    const res = await authFetch(`/research/experiments?limit=${limit}`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching experiments:", err);
  }
  return [];
}

export async function getFeatures(
  symbol = "BTC_USDT",
  timeframe = "1h"
): Promise<FeatureRecord[]> {
  try {
    const res = await authFetch(
      `/research/features?symbol=${symbol}&timeframe=${timeframe}`
    );
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching features:", err);
  }
  return [];
}

export async function getHypotheses(limit = 50): Promise<HypothesisTest[]> {
  try {
    const res = await authFetch(`/research/hypotheses?limit=${limit}`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching hypotheses:", err);
  }
  return [];
}

export async function runResearch(
  symbol = "BTC_USDT",
  timeframe = "1h",
  population?: number
): Promise<ResearchRunResult | null> {
  try {
    const res = await authFetch(`/research/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, timeframe, population }),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error running research:", err);
  }
  return null;
}

export async function recomputeFeatures(
  symbol = "BTC_USDT",
  timeframe = "1h"
): Promise<FeatureRecord[]> {
  try {
    const res = await authFetch(
      `/research/features/recompute?symbol=${symbol}&timeframe=${timeframe}`,
      { method: "POST" }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error recomputing features:", err);
  }
  return [];
}

export async function testHypotheses(
  symbol = "BTC_USDT",
  timeframe = "1h"
): Promise<HypothesisTest[]> {
  try {
    const res = await authFetch(
      `/research/hypotheses/test?symbol=${symbol}&timeframe=${timeframe}`,
      { method: "POST" }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error testing hypotheses:", err);
  }
  return [];
}

export async function promoteStrategy(
  strategyId: number
): Promise<PromotionResult | null> {
  try {
    const res = await authFetch(`/research/promote/${strategyId}`, {
      method: "POST",
    });
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error promoting strategy:", err);
  }
  return null;
}

export async function getStrategyDetail(id: number): Promise<StrategyDetail | null> {
  try {
    const res = await authFetch(`/research/strategies/${id}/detail`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching strategy detail:", err);
  }
  return null;
}

export async function getABTests(limit = 50): Promise<ABTest[]> {
  try {
    const res = await authFetch(`/research/ab-tests?limit=${limit}`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching AB tests:", err);
  }
  return [];
}

export async function getResearchSymbols(): Promise<ResearchSymbol[]> {
  try {
    const res = await authFetch(`/research/symbols`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching symbols:", err);
  }
  return [];
}

export async function testCustomHypothesis(
  statement: string, feature: string, conditionDesc: string,
  expectsNegative: boolean, symbol: string, timeframe: string
): Promise<HypothesisTest | null> {
  try {
    const res = await authFetch(`/research/hypotheses/custom`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ statement, feature, condition_desc: conditionDesc, expects_negative: expectsNegative, symbol, timeframe }),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error testing custom hypothesis:", err);
  }
  return null;
}
