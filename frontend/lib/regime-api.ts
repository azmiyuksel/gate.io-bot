import type { RegimeConfidence, RegimePerformance, RegimeStatus, RegimeTransition } from "@/types/regime";
import { authFetch } from "@/lib/auth-api";

export async function getCurrentRegime(symbol: string = "BTC_USDT", timeframe: string = "1h"): Promise<RegimeStatus | null> {
  try {
    const res = await authFetch(`/regime/current?symbol=${symbol}&timeframe=${timeframe}`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching current regime:", err);
  }
  return null;
}

export async function getRegimeHistory(symbol: string = "BTC_USDT", timeframe: string = "1h"): Promise<RegimeStatus[]> {
  try {
    const res = await authFetch(`/regime/history?symbol=${symbol}&timeframe=${timeframe}`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching regime history:", err);
  }
  return [];
}

export async function getConfidenceHistory(symbol: string = "BTC_USDT"): Promise<RegimeConfidence[]> {
  try {
    const res = await authFetch(`/regime/confidence?symbol=${symbol}`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching confidence history:", err);
  }
  return [];
}

export async function getRegimePerformance(): Promise<RegimePerformance[]> {
  try {
    const res = await authFetch(`/regime/performance`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching regime performance:", err);
  }
  return [];
}

export async function recalculateRegime(symbol: string = "BTC_USDT", timeframe: string = "1h"): Promise<boolean> {
  try {
    const res = await authFetch(`/regime/recalculate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, timeframe }),
    });
    return res.ok;
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error recalculating regime:", err);
  }
  return false;
}

export async function getRegimeTransitions(symbol: string = "BTC_USDT"): Promise<RegimeTransition[]> {
  try {
    const res = await authFetch(`/regime/transitions?symbol=${symbol}`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error("Error fetching regime transitions:", err);
  }
  return [];
}
