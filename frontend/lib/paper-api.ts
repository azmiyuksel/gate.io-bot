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

export function createPaperStream(
  onData: (data: PaperStatus) => void,
  onClose?: () => void,
): PaperStream {
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
      onClose?.();
    },
  };
}

async function _actionFetch(path: string, body?: unknown): Promise<boolean> {
  const res = await authFetch(path, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `İşlem başarısız (HTTP ${res.status})`;
    try {
      const errBody = await res.json();
      if (errBody?.detail) detail = errBody.detail;
      else if (errBody?.error) detail = errBody.error;
    } catch {
      /* response had no JSON body */
    }
    throw new Error(detail);
  }
  return true;
}

export async function startPaperTrading(
  config?: { account_name?: string; initial_balance?: number; symbols?: string[] },
): Promise<boolean> {
  return _actionFetch(`/paper/start`, config ?? {});
}

export async function stopPaperTrading(): Promise<boolean> {
  return _actionFetch(`/paper/stop`);
}

export async function pausePaperTrading(): Promise<boolean> {
  return _actionFetch(`/paper/pause`);
}

export async function resumePaperTrading(): Promise<boolean> {
  return _actionFetch(`/paper/resume`);
}

export async function resetPaperTrading(): Promise<boolean> {
  return _actionFetch(`/paper/reset`);
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
  const res = await authFetch(`/paper/manual-order`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, side, quantity }),
  });
  if (!res.ok) {
    // Surface the server's error reason (e.g. "could not fetch current market
    // price") so the toast is informative instead of a generic failure.
    let detail = `İşlem başarısız (HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (body?.error) detail = body.error;
    } catch {
      /* response had no JSON body */
    }
    throw new Error(detail);
  }
  return true;
}

export async function closePaperPosition(positionId: number): Promise<boolean> {
  const res = await authFetch(`/paper/close-position/${positionId}`, { method: "POST" });
  if (!res.ok) {
    let detail = `Kapatma başarısız (HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (body?.error) detail = body.error;
    } catch {
      /* response had no JSON body */
    }
    throw new Error(detail);
  }
  return true;
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
