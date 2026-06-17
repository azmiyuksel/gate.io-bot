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
import { authFetch, getFreshAccessToken } from "@/lib/auth-api";

export interface PaperStream {
  close: () => void;
}

export function createPaperStream(onData: (data: PaperStatus) => void): PaperStream {
  const publicUrl = process.env.NEXT_PUBLIC_API_URL || "";
  const baseUrl = publicUrl || "";

  let es: EventSource | null = null;
  let closed = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectDelay = 1000;
  const maxReconnectDelay = 30000;

  function scheduleReconnect() {
    if (closed) return;
    reconnectTimer = setTimeout(() => void connect(), reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, maxReconnectDelay);
  }

  async function connect() {
    if (closed) return;
    // EventSource cannot set an Authorization header, so the short-lived access
    // token rides in the query string. It must be FRESH on every (re)connect —
    // otherwise an expired token makes the stream 401 ("invalid token") forever,
    // even while normal authFetch calls keep working via their 401-refresh.
    const token = await getFreshAccessToken();
    if (closed) return;
    if (!token) {
      scheduleReconnect();
      return;
    }
    const url = `${baseUrl}/api/v1/paper/stream?token=${encodeURIComponent(token)}`;
    es = new EventSource(url);
    es.onmessage = (event) => {
      reconnectDelay = 1000;
      try {
        const data = JSON.parse(event.data);
        if (data.status !== "error") {
          onData(data as PaperStatus);
        }
      } catch {
        // ignore parse errors
      }
    };
    es.onerror = () => {
      // An expired-token 401 surfaces here too; reconnect re-mints the token.
      es?.close();
      es = null;
      scheduleReconnect();
    };
  }

  void connect();

  return {
    close() {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      es?.close();
      es = null;
    },
  };
}

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

export async function manualPaperOrder(symbol: string, side: "buy" | "sell", quantity: number): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/manual-order`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, side, quantity }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function closePaperPosition(positionId: number): Promise<boolean> {
  try {
    const res = await authFetch(`/paper/close-position/${positionId}`, { method: "POST" });
    return res.ok;
  } catch {
    return false;
  }
}

export async function getPaperExitStats(): Promise<{ counts: Record<string, number>; total_closed: number } | null> {
  try {
    const res = await authFetch(`/paper/exit-stats`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
