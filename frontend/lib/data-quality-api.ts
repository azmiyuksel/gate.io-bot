import type {
  DataQualityReport,
  DataQualityStatus,
  MarketDataAnomaly,
  MarketDataHealthLog,
  RevalidateResult,
} from "@/types/data-quality";
import { authFetch } from "@/lib/auth-api";

export async function getDataQualityStatus(
  symbol: string,
  timeframe: string = "1h"
): Promise<DataQualityStatus | null> {
  try {
    const res = await authFetch(
      `/data-quality/status?symbol=${symbol}&timeframe=${timeframe}`
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching data quality status for ${symbol}:`, err);
  }
  return null;
}

export async function getDataQualityAnomalies(
  symbol: string,
  timeframe: string = "1h",
  limit: number = 100
): Promise<MarketDataAnomaly[]> {
  try {
    const res = await authFetch(
      `/data-quality/anomalies?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}`
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching anomalies for ${symbol}:`, err);
  }
  return [];
}

export async function getDataQualityHealthLogs(
  symbol: string,
  timeframe: string = "1h",
  limit: number = 200
): Promise<MarketDataHealthLog[]> {
  try {
    const res = await authFetch(
      `/data-quality/health-logs?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}`
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching health logs for ${symbol}:`, err);
  }
  return [];
}

export async function getDataQualityReport(
  symbol: string,
  timeframe: string = "1h",
  hours: number = 24
): Promise<DataQualityReport | null> {
  try {
    const res = await authFetch(
      `/data-quality/report?symbol=${symbol}&timeframe=${timeframe}&hours=${hours}`
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching data quality report for ${symbol}:`, err);
  }
  return null;
}

export async function revalidateDataQuality(
  symbol: string,
  timeframe: string = "1h",
  limit: number = 240
): Promise<RevalidateResult | null> {
  try {
    const res = await authFetch(`/data-quality/revalidate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, timeframe, limit }),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error revalidating data quality for ${symbol}:`, err);
  }
  return null;
}
