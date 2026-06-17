"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Card } from "@/components/ui/card";
import { fmtPrice } from "@/lib/utils";

/**
 * Live price panel. Connects DIRECTLY to Gate.io's public WebSocket
 * (spot.tickers) from the browser — no auth, no backend dependency — so the
 * rates update in real time (push) regardless of which backend workers run.
 * WebSockets are not subject to CORS, and the app sets no CSP, so this is safe.
 */

const GATEIO_WS = "wss://api.gateio.ws/ws/v4/";

// Curated, liquid majors shown by default. Override via the `symbols` prop.
export const DEFAULT_TICKER_SYMBOLS = [
  "BTC_USDT", "ETH_USDT", "BNB_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT",
  "ADA_USDT", "AVAX_USDT", "LINK_USDT", "TRX_USDT", "DOT_USDT", "LTC_USDT",
];

interface Tick {
  last: number;
  changePct: number; // 24h change %
}

type Status = "connecting" | "live" | "reconnecting";

interface Props {
  symbols?: string[];
  title?: string;
}

export default function LivePrices({ symbols = DEFAULT_TICKER_SYMBOLS, title = "Canlı Kurlar" }: Props) {
  const [ticks, setTicks] = useState<Record<string, Tick>>({});
  const [status, setStatus] = useState<Status>("connecting");
  const wsRef = useRef<WebSocket | null>(null);
  const flashRef = useRef<Record<string, "up" | "down">>({});

  // Stable key so the effect doesn't reconnect on every render.
  const symbolsKey = useMemo(() => symbols.join(","), [symbols]);

  useEffect(() => {
    const subSymbols = symbolsKey.split(",");
    let closed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    const connect = () => {
      if (closed) return;
      let ws: WebSocket;
      try {
        ws = new WebSocket(GATEIO_WS);
      } catch {
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        attempt = 0;
        setStatus("live");
        ws.send(
          JSON.stringify({
            time: Math.floor(Date.now() / 1000),
            channel: "spot.tickers",
            event: "subscribe",
            payload: subSymbols,
          }),
        );
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          const r = msg?.result;
          if (!r || !r.currency_pair || r.last == null) return;
          const last = Number(r.last);
          if (!Number.isFinite(last)) return;
          const changePct = Number(r.change_percentage ?? 0);
          setTicks((prev) => {
            const old = prev[r.currency_pair];
            if (old) flashRef.current[r.currency_pair] = last >= old.last ? "up" : "down";
            return { ...prev, [r.currency_pair]: { last, changePct } };
          });
        } catch {
          /* ignore malformed frames */
        }
      };

      ws.onclose = () => {
        if (!closed) scheduleReconnect();
      };
      ws.onerror = () => {
        ws.close();
      };
    };

    const scheduleReconnect = () => {
      if (closed) return;
      setStatus("reconnecting");
      attempt += 1;
      const delay = Math.min(1000 * 2 ** attempt, 15000);
      reconnectTimer = setTimeout(connect, delay);
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [symbolsKey]);

  const statusLabel =
    status === "live" ? "Canlı" : status === "connecting" ? "Bağlanıyor…" : "Yeniden bağlanıyor…";
  const statusColor = status === "live" ? "bg-green-500" : "bg-amber-500";

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold">{title}</h2>
        <span className="flex items-center gap-1.5 text-xs text-muted">
          <span className={`h-2 w-2 rounded-full ${statusColor} ${status === "live" ? "animate-pulse" : ""}`} />
          {statusLabel}
          <span className="ml-1 hidden sm:inline">· Gate.io</span>
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {symbolsKey.split(",").map((sym) => {
          const t = ticks[sym];
          const up = (t?.changePct ?? 0) >= 0;
          const flash = flashRef.current[sym];
          const base = sym.replace("_USDT", "");
          return (
            <div
              key={sym}
              className="rounded-md border border-border px-3 py-2"
              title={sym.replace("_", " / ")}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">{base}</span>
                <span className="text-[10px] text-muted">/USDT</span>
              </div>
              {t ? (
                <>
                  <div
                    className={`mt-0.5 font-mono text-sm tabular-nums transition-colors ${
                      flash === "up" ? "text-primary" : flash === "down" ? "text-danger" : "text-foreground"
                    }`}
                  >
                    ${fmtPrice(t.last)}
                  </div>
                  <div className={`text-xs font-medium ${up ? "text-primary" : "text-danger"}`}>
                    {up ? "▲" : "▼"} {Math.abs(t.changePct).toFixed(2)}%
                    <span className="ml-1 text-[10px] font-normal text-muted">24s</span>
                  </div>
                </>
              ) : (
                <div className="mt-1 h-7 animate-pulse rounded bg-border/60" />
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[10px] text-muted">
        Veriler Gate.io spot piyasasından canlı alınır; gecikmeli olabilir, yatırım tavsiyesi değildir.
      </p>
    </Card>
  );
}
