import type {
  StrategyHealthStatus,
  StrategyBaseline,
  StrategyHealthLog,
  StrategyAlert,
  StrategyStateTransition,
} from "@/types/health";
import { authFetch } from "@/lib/auth-api";

export async function getStrategyHealth(
  strategyName: string
): Promise<StrategyHealthStatus | null> {
  try {
    const res = await authFetch(`/strategy-health/${strategyName}`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`Error fetching strategy health for ${strategyName}:`, err);
  }
  return null;
}

export async function getHealthMetrics(
  strategyName: string
): Promise<StrategyHealthLog[]> {
  try {
    const res = await authFetch(`/strategy-health/${strategyName}/metrics`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`Error fetching health metrics for ${strategyName}:`, err);
  }
  return [];
}

export async function getStrategyAlerts(
  strategyName: string
): Promise<StrategyAlert[]> {
  try {
    const res = await authFetch(`/strategy-health/${strategyName}/alerts`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`Error fetching strategy alerts for ${strategyName}:`, err);
  }
  return [];
}

export async function recalculateStrategyHealth(
  strategyName: string
): Promise<StrategyHealthStatus | null> {
  try {
    const res = await authFetch(`/strategy-health/${strategyName}/recalculate`, {
      method: "POST",
    });
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`Error recalculating strategy health for ${strategyName}:`, err);
  }
  return null;
}

export async function pauseStrategy(
  strategyName: string
): Promise<boolean> {
  try {
    const res = await authFetch(`/strategy-health/${strategyName}/pause`, {
      method: "POST",
    });
    return res.ok;
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`Error pausing strategy ${strategyName}:`, err);
  }
  return false;
}

export async function resumeStrategy(
  strategyName: string
): Promise<boolean> {
  try {
    const res = await authFetch(`/strategy-health/${strategyName}/resume`, {
      method: "POST",
    });
    return res.ok;
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`Error resuming strategy ${strategyName}:`, err);
  }
  return false;
}

export async function getStrategyBaseline(
  strategyName: string
): Promise<StrategyBaseline | null> {
  try {
    const res = await authFetch(`/strategy-health/${strategyName}/baseline`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`Error fetching strategy baseline for ${strategyName}:`, err);
  }
  return null;
}

export async function getTransitions(
  strategyName: string
): Promise<StrategyStateTransition[]> {
  try {
    const res = await authFetch(`/strategy-health/${strategyName}/transitions`);
    if (res.ok) return await res.json();
  } catch (err) {
    if (process.env.NODE_ENV !== "production") console.error(`Error fetching state transitions for ${strategyName}:`, err);
  }
  return [];
}
