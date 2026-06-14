import type {
  PaperEconomics,
  PaperEquityPoint,
  PaperLog,
  PaperMetrics,
  PaperOrder,
  PaperPosition,
  PaperRiskStatus,
  PaperSignalDiagnostics,
  PaperStatus,
  PaperTrade,
} from "@/types/paper";
import { authFetch } from "@/lib/auth-api";

export async function startPaperTrading(
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

export async function stopPaperTrading(): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/stop`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function pausePaperTrading(): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/pause`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function resumePaperTrading(): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/resume`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function resetPaperTrading(): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/reset`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function getPaperStatus(): Promise<PaperStatus | null> {
  try {
    const res = await authFetch(`/paper/status`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getPaperPositions(): Promise<PaperPosition[]> {
  try {
    const res = await authFetch(`/paper/positions`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperTrades(): Promise<PaperTrade[]> {
  try {
    const res = await authFetch(`/paper/trades`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperOrders(): Promise<PaperOrder[]> {
  try {
    const res = await authFetch(`/paper/orders`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperEquity(): Promise<PaperEquityPoint[]> {
  try {
    const res = await authFetch(`/paper/equity`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperMetrics(): Promise<PaperMetrics | null> {
  try {
    const res = await authFetch(`/paper/metrics`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getPaperRiskStatus(): Promise<PaperRiskStatus | null> {
  try {
    const res = await authFetch(`/paper/risk`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getPaperLogs(): Promise<PaperLog[]> {
  try {
    const res = await authFetch(`/paper/logs`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperSignalDiagnostics(
  hours = 24,
): Promise<PaperSignalDiagnostics | null> {
  try {
    const res = await authFetch(`/paper/signal-diagnostics?hours=${hours}`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getPaperEconomics(): Promise<PaperEconomics | null> {
  try {
    const res = await authFetch(`/paper/economics`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
