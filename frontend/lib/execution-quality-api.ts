import type {
  ExecutionQualityStatus,
  ExecutionSlippageLog,
  ExecutionLatencyLog,
  ExecutionReport,
} from "@/types/execution-quality";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function headers(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export async function getStrategyExecutionStatus(
  token: string,
  strategyName: string
): Promise<ExecutionQualityStatus | null> {
  try {
    const res = await fetch(`${apiUrl}/execution-quality/${strategyName}`, {
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching execution status for ${strategyName}:`, err);
  }
  return null;
}

export async function getSlippageLogs(
  token: string,
  strategyName: string = "capital_preservation_v1",
  limit: number = 100
): Promise<ExecutionSlippageLog[]> {
  try {
    const res = await fetch(
      `${apiUrl}/execution-quality/slippage/logs?strategy_name=${strategyName}&limit=${limit}`,
      { headers: headers(token) }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching slippage logs for ${strategyName}:`, err);
  }
  return [];
}

export async function getLatencyLogs(
  token: string,
  strategyName: string = "capital_preservation_v1",
  limit: number = 100
): Promise<ExecutionLatencyLog[]> {
  try {
    const res = await fetch(
      `${apiUrl}/execution-quality/latency/logs?strategy_name=${strategyName}&limit=${limit}`,
      { headers: headers(token) }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching latency logs for ${strategyName}:`, err);
  }
  return [];
}

export async function getExecutionReport(
  token: string,
  strategyName: string = "capital_preservation_v1",
  days: number = 30
): Promise<ExecutionReport | null> {
  try {
    const res = await fetch(
      `${apiUrl}/execution-quality/report/logs?strategy_name=${strategyName}&days=${days}`,
      { headers: headers(token) }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching execution report for ${strategyName}:`, err);
  }
  return null;
}

export async function recalculateExecutionQuality(
  token: string,
  strategyName: string = "capital_preservation_v1"
): Promise<ExecutionQualityStatus | null> {
  try {
    const res = await fetch(
      `${apiUrl}/execution-quality/recalculate?strategy_name=${strategyName}`,
      {
        method: "POST",
        headers: headers(token),
      }
    );
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error recalculating execution quality for ${strategyName}:`, err);
  }
  return null;
}
