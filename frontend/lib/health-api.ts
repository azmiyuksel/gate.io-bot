import type {
  StrategyHealthStatus,
  StrategyBaseline,
  StrategyHealthLog,
  StrategyAlert,
  StrategyStateTransition,
} from "@/types/health";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function headers(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export async function getStrategyHealth(
  token: string,
  strategyName: string
): Promise<StrategyHealthStatus | null> {
  try {
    const res = await fetch(`${apiUrl}/strategy-health/${strategyName}`, {
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching strategy health for ${strategyName}:`, err);
  }
  return null;
}

export async function getHealthMetrics(
  token: string,
  strategyName: string
): Promise<StrategyHealthLog[]> {
  try {
    const res = await fetch(`${apiUrl}/strategy-health/${strategyName}/metrics`, {
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching health metrics for ${strategyName}:`, err);
  }
  return [];
}

export async function getStrategyAlerts(
  token: string,
  strategyName: string
): Promise<StrategyAlert[]> {
  try {
    const res = await fetch(`${apiUrl}/strategy-health/${strategyName}/alerts`, {
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching strategy alerts for ${strategyName}:`, err);
  }
  return [];
}

export async function recalculateStrategyHealth(
  token: string,
  strategyName: string
): Promise<StrategyHealthStatus | null> {
  try {
    const res = await fetch(`${apiUrl}/strategy-health/${strategyName}/recalculate`, {
      method: "POST",
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error recalculating strategy health for ${strategyName}:`, err);
  }
  return null;
}

export async function pauseStrategy(
  token: string,
  strategyName: string
): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/strategy-health/${strategyName}/pause`, {
      method: "POST",
      headers: headers(token),
    });
    return res.ok;
  } catch (err) {
    console.error(`Error pausing strategy ${strategyName}:`, err);
  }
  return false;
}

export async function resumeStrategy(
  token: string,
  strategyName: string
): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/strategy-health/${strategyName}/resume`, {
      method: "POST",
      headers: headers(token),
    });
    return res.ok;
  } catch (err) {
    console.error(`Error resuming strategy ${strategyName}:`, err);
  }
  return false;
}

export async function getStrategyBaseline(
  token: string,
  strategyName: string
): Promise<StrategyBaseline | null> {
  try {
    const res = await fetch(`${apiUrl}/strategy-health/${strategyName}/baseline`, {
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching strategy baseline for ${strategyName}:`, err);
  }
  return null;
}

export async function getTransitions(
  token: string,
  strategyName: string
): Promise<StrategyStateTransition[]> {
  try {
    const res = await fetch(`${apiUrl}/strategy-health/${strategyName}/transitions`, {
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error(`Error fetching state transitions for ${strategyName}:`, err);
  }
  return [];
}
