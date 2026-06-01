import type {
  DataQualityReport,
  DataQualityStatus,
  MarketDataAnomaly,
  MarketDataHealthLog,
  RevalidateResult,
} from "@/types/data-quality";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function headers(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export async function getDataQualityStatus(
  token: string,
  symbol: string,
  timeframe: string = "1h"
): Promise<DataQualityStatus | null> {
  try {
    const res = await fetch(
      `${apiUrl}/data-quality/status?symbol=${symbol}&timeframe=${timeframe}`,
      { headers: headers(token) }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching data quality status for ${symbol}:`, err);
  }
  return null;
}

export async function getDataQualityAnomalies(
  token: string,
  symbol: string,
  timeframe: string = "1h",
  limit: number = 100
): Promise<MarketDataAnomaly[]> {
  try {
    const res = await fetch(
      `${apiUrl}/data-quality/anomalies?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}`,
      { headers: headers(token) }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching anomalies for ${symbol}:`, err);
  }
  return [];
}

export async function getDataQualityHealthLogs(
  token: string,
  symbol: string,
  timeframe: string = "1h",
  limit: number = 200
): Promise<MarketDataHealthLog[]> {
  try {
    const res = await fetch(
      `${apiUrl}/data-quality/health-logs?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}`,
      { headers: headers(token) }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching health logs for ${symbol}:`, err);
  }
  return [];
}

export async function getDataQualityReport(
  token: string,
  symbol: string,
  timeframe: string = "1h",
  hours: number = 24
): Promise<DataQualityReport | null> {
  try {
    const res = await fetch(
      `${apiUrl}/data-quality/report?symbol=${symbol}&timeframe=${timeframe}&hours=${hours}`,
      { headers: headers(token) }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching data quality report for ${symbol}:`, err);
  }
  return null;
}

export async function revalidateDataQuality(
  token: string,
  symbol: string,
  timeframe: string = "1h",
  limit: number = 240
): Promise<RevalidateResult | null> {
  try {
    const res = await fetch(`${apiUrl}/data-quality/revalidate`, {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify({ symbol, timeframe, limit }),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error revalidating data quality for ${symbol}:`, err);
  }
  return null;
}
