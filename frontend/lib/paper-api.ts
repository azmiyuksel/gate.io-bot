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

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

function headers(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

export async function startPaperTrading(
  token: string,
  config?: { account_name?: string; initial_balance?: number; symbols?: string[] },
): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/paper/start`, {
      method: "POST",
      headers: headers(token),
      body: JSON.stringify(config ?? {}),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function stopPaperTrading(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/paper/stop`, { method: "POST", headers: headers(token) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function pausePaperTrading(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/paper/pause`, { method: "POST", headers: headers(token) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function resumePaperTrading(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/paper/resume`, { method: "POST", headers: headers(token) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function resetPaperTrading(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${apiUrl}/paper/reset`, { method: "POST", headers: headers(token) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function getPaperStatus(token: string): Promise<PaperStatus | null> {
  try {
    const res = await fetch(`${apiUrl}/paper/status`, { headers: headers(token) });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getPaperPositions(token: string): Promise<PaperPosition[]> {
  try {
    const res = await fetch(`${apiUrl}/paper/positions`, { headers: headers(token) });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperTrades(token: string): Promise<PaperTrade[]> {
  try {
    const res = await fetch(`${apiUrl}/paper/trades`, { headers: headers(token) });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperOrders(token: string): Promise<PaperOrder[]> {
  try {
    const res = await fetch(`${apiUrl}/paper/orders`, { headers: headers(token) });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperEquity(token: string): Promise<PaperEquityPoint[]> {
  try {
    const res = await fetch(`${apiUrl}/paper/equity`, { headers: headers(token) });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function getPaperMetrics(token: string): Promise<PaperMetrics | null> {
  try {
    const res = await fetch(`${apiUrl}/paper/metrics`, { headers: headers(token) });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getPaperRiskStatus(token: string): Promise<PaperRiskStatus | null> {
  try {
    const res = await fetch(`${apiUrl}/paper/risk`, { headers: headers(token) });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function getPaperLogs(token: string): Promise<PaperLog[]> {
  try {
    const res = await fetch(`${apiUrl}/paper/logs`, { headers: headers(token) });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}
