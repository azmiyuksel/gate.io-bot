import type {
  PaperEquityPoint,
  PaperLog,
  PaperMetrics,
  PaperOrder,
  PaperPosition,
  PaperRiskStatus,
  PaperStatus,
  PaperTrade,
} from "@/types/paper";
import { authFetch } from "@/lib/auth-api";

export async function startPaperTrading(
  token: string,
  config?: { account_name?: string; initial_balance?: number; symbols?: string[] },
): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config ?? {}),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function stopPaperTrading(token: string): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/stop`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function pausePaperTrading(token: string): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/pause`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function resumePaperTrading(token: string): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/resume`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function resetPaperTrading(token: string): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/reset`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function getPaperStatus(token: string): Promise<PaperStatus | null> {
  try {
    const res = await authFetch(`/paper/status`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getPaperPositions(token: string): Promise<PaperPosition[]> {
  try {
    const res = await authFetch(`/paper/positions`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperTrades(token: string): Promise<PaperTrade[]> {
  try {
    const res = await authFetch(`/paper/trades`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperOrders(token: string): Promise<PaperOrder[]> {
  try {
    const res = await authFetch(`/paper/orders`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperEquity(token: string): Promise<PaperEquityPoint[]> {
  try {
    const res = await authFetch(`/paper/equity`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperMetrics(token: string): Promise<PaperMetrics | null> {
  try {
    const res = await authFetch(`/paper/metrics`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getPaperRiskStatus(token: string): Promise<PaperRiskStatus | null> {
  try {
    const res = await authFetch(`/paper/risk`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getPaperLogs(token: string): Promise<PaperLog[]> {
  try {
    const res = await authFetch(`/paper/logs`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}
