import type {
  Allocation,
  Portfolio,
  PortfolioCorrelations,
  PortfolioMetric,
  RebalanceEvent,
  RiskSnapshot,
  StrategyPerformance,
} from "@/types/portfolio";
import { authFetch } from "@/lib/auth-api";

export async function getPortfolio(): Promise<Portfolio | null> {
  try {
    const res = await authFetch(`/portfolio`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching portfolio:", err);
  }
  return null;
}

export async function getPortfolioCorrelations(): Promise<PortfolioCorrelations | null> {
  try {
    const res = await authFetch(`/portfolio/correlations`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching correlations:", err);
  }
  return null;
}

export async function getPortfolioMetrics(): Promise<PortfolioMetric[]> {
  try {
    const res = await authFetch(`/portfolio/metrics`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching portfolio metrics:", err);
  }
  return [];
}

export async function getPortfolioAllocations(): Promise<Allocation[]> {
  try {
    const res = await authFetch(`/portfolio/allocations`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching portfolio allocations:", err);
  }
  return [];
}

export async function getPortfolioVaR(): Promise<{ var: number; cvar: number } | null> {
  try {
    const res = await authFetch(`/portfolio/var`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching VaR:", err);
  }
  return null;
}

export async function getStrategyPerformance(): Promise<StrategyPerformance[]> {
  try {
    const res = await authFetch(`/portfolio/strategy-performance`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching strategy performance:", err);
  }
  return [];
}

export async function triggerRebalance(): Promise<boolean> {
  try {
    const res = await authFetch(`/portfolio/rebalance`, {
      method: "POST",
    });
    return res.ok;
  } catch (err) {
    console.error("Error triggering rebalance:", err);
  }
  return false;
}

export async function resetPortfolio(): Promise<boolean> {
  try {
    const res = await authFetch(`/portfolio/reset`, {
      method: "POST",
    });
    return res.ok;
  } catch (err) {
    console.error("Error resetting portfolio:", err);
  }
  return false;
}

export async function runStressTest(scenarioName: string): Promise<RiskSnapshot | null> {
  try {
    const res = await authFetch(`/portfolio/stress-test?scenario_name=${encodeURIComponent(scenarioName)}`, {
      method: "POST",
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error running stress test:", err);
  }
  return null;
}

export async function getRebalanceHistory(): Promise<RebalanceEvent[]> {
  try {
    const res = await authFetch(`/portfolio/rebalances`);
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching rebalance history:", err);
  }
  return [];
}
