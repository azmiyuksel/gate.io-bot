import type { Allocation, Portfolio, PortfolioMetric, RebalanceEvent, RiskSnapshot } from "@/types/portfolio";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function headers(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export async function getPortfolio(token: string): Promise<Portfolio | null> {
  try {
    const res = await fetch(`${apiUrl}/portfolio`, { headers: headers(token) });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching portfolio:", err);
  }
  return null;
}

export async function getPortfolioMetrics(token: string): Promise<PortfolioMetric[]> {
  try {
    const res = await fetch(`${apiUrl}/portfolio/metrics`, { headers: headers(token) });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching portfolio metrics:", err);
  }
  return [];
}

export async function getPortfolioAllocations(token: string): Promise<Allocation[]> {
  try {
    const res = await fetch(`${apiUrl}/portfolio/allocations`, { headers: headers(token) });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching portfolio allocations:", err);
  }
  return [];
}

export async function triggerRebalance(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/portfolio/rebalance`, {
      method: "POST",
      headers: headers(token),
    });
    return res.ok;
  } catch (err) {
    console.error("Error triggering rebalance:", err);
  }
  return false;
}

export async function resetPortfolio(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/portfolio/reset`, {
      method: "POST",
      headers: headers(token),
    });
    return res.ok;
  } catch (err) {
    console.error("Error resetting portfolio:", err);
  }
  return false;
}

export async function runStressTest(token: string, scenarioName: string): Promise<RiskSnapshot | null> {
  try {
    const res = await fetch(`${apiUrl}/portfolio/stress-test?scenario_name=${scenarioName}`, {
      method: "POST",
      headers: headers(token),
    });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error running stress test:", err);
  }
  return null;
}

export async function getRebalanceHistory(token: string): Promise<RebalanceEvent[]> {
  try {
    const res = await fetch(`${apiUrl}/portfolio/rebalances`, { headers: headers(token) });
    if (res.ok) return await res.json();
  } catch (err) {
    console.error("Error fetching rebalance history:", err);
  }
  return [];
}
