import type {
  FeatureRecord,
  HypothesisTest,
  PromotionResult,
  ResearchExperiment,
  ResearchRunResult,
  ResearchStrategy,
  StrategyVersion,
} from "@/types/strategy-research";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function headers(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export async function getStrategies(token: string, status?: string): Promise<ResearchStrategy[]> {
  try {
    const qs = status ? `?status=${status}` : "";
    const res = await fetch(`${apiUrl}/research/strategies${qs}`, { headers: headers(token) });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching strategies:", err);
  }
  return [];
}

export async function getLeaderboard(token: string, limit = 25): Promise<StrategyVersion[]> {
  try {
    const res = await fetch(`${apiUrl}/research/leaderboard?limit=${limit}`, {
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching leaderboard:", err);
  }
  return [];
}

export async function getExperiments(token: string, limit = 100): Promise<ResearchExperiment[]> {
  try {
    const res = await fetch(`${apiUrl}/research/experiments?limit=${limit}`, {
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching experiments:", err);
  }
  return [];
}

export async function getFeatures(
  token: string,
  symbol = "BTC_USDT",
  timeframe = "1h"
): Promise<FeatureRecord[]> {
  try {
    const res = await fetch(
      `${apiUrl}/research/features?symbol=${symbol}&timeframe=${timeframe}`,
      { headers: headers(token) }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching features:", err);
  }
  return [];
}

export async function getHypotheses(token: string, limit = 50): Promise<HypothesisTest[]> {
  try {
    const res = await fetch(`${apiUrl}/research/hypotheses?limit=${limit}`, {
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching hypotheses:", err);
  }
  return [];
}

export async function runResearch(
  token: string,
  symbol = "BTC_USDT",
  timeframe = "1h",
  population?: number
): Promise<ResearchRunResult | null> {
  try {
    const res = await fetch(`${apiUrl}/research/run`, {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify({ symbol, timeframe, population }),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error running research:", err);
  }
  return null;
}

export async function recomputeFeatures(
  token: string,
  symbol = "BTC_USDT",
  timeframe = "1h"
): Promise<FeatureRecord[]> {
  try {
    const res = await fetch(
      `${apiUrl}/research/features/recompute?symbol=${symbol}&timeframe=${timeframe}`,
      { method: "POST", headers: headers(token) }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error recomputing features:", err);
  }
  return [];
}

export async function testHypotheses(
  token: string,
  symbol = "BTC_USDT",
  timeframe = "1h"
): Promise<HypothesisTest[]> {
  try {
    const res = await fetch(
      `${apiUrl}/research/hypotheses/test?symbol=${symbol}&timeframe=${timeframe}`,
      { method: "POST", headers: headers(token) }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error testing hypotheses:", err);
  }
  return [];
}

export async function promoteStrategy(
  token: string,
  strategyId: number
): Promise<PromotionResult | null> {
  try {
    const res = await fetch(`${apiUrl}/research/promote/${strategyId}`, {
      method: "POST",
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error promoting strategy:", err);
  }
  return null;
}
