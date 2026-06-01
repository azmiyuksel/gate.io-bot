import type { RegimeConfidence, RegimePerformance, RegimeStatus, RegimeTransition } from "@/types/regime";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function headers(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export async function getCurrentRegime(token: string, symbol: string = "BTC_USDT", timeframe: string = "1h"): Promise<RegimeStatus | null> {
  try {
    const res = await fetch(`${apiUrl}/regime/current?symbol=${symbol}&timeframe=${timeframe}`, { headers: headers(token) });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching current regime:", err);
  }
  return null;
}

export async function getRegimeHistory(token: string, symbol: string = "BTC_USDT", timeframe: string = "1h"): Promise<RegimeStatus[]> {
  try {
    const res = await fetch(`${apiUrl}/regime/history?symbol=${symbol}&timeframe=${timeframe}`, { headers: headers(token) });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching regime history:", err);
  }
  return [];
}

export async function getConfidenceHistory(token: string, symbol: string = "BTC_USDT"): Promise<RegimeConfidence[]> {
  try {
    const res = await fetch(`${apiUrl}/regime/confidence?symbol=${symbol}`, { headers: headers(token) });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching confidence history:", err);
  }
  return [];
}

export async function getRegimePerformance(token: string): Promise<RegimePerformance[]> {
  try {
    const res = await fetch(`${apiUrl}/regime/performance`, { headers: headers(token) });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching regime performance:", err);
  }
  return [];
}

export async function recalculateRegime(token: string, symbol: string = "BTC_USDT", timeframe: string = "1h"): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/regime/recalculate`, {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify({ symbol, timeframe }),
    });
    return res.ok;
  } catch (err) {
    console.error("Error recalculating regime:", err);
  }
  return false;
}

export async function getRegimeTransitions(token: string, symbol: string = "BTC_USDT"): Promise<RegimeTransition[]> {
  try {
    const res = await fetch(`${apiUrl}/regime/transitions?symbol=${symbol}`, { headers: headers(token) });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching regime transitions:", err);
  }
  return [];
}
