"use client";

import { Plus, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { manualPaperOrder } from "@/lib/paper-api";

type ActionFn = (fn: () => Promise<boolean>, successMsg: string, btnId?: string) => Promise<void>;
type ToastFn = (msg: string, type: "success" | "error") => void;

interface Props {
  symbol: string;
  side: "buy" | "sell";
  qty: string;
  onSymbolChange: (s: string) => void;
  onSideChange: (s: "buy" | "sell") => void;
  onQtyChange: (q: string) => void;
  actionLoadingBtn: string;
  onAction: ActionFn;
  toast: ToastFn;
}

// Shared with LivePrices (DEFAULT_TICKER_SYMBOLS) — keep in sync.
const SYMBOLS = ["BTC_USDT", "ETH_USDT", "BNB_USDT", "SOL_USDT", "XRP_USDT", "DOGE_USDT", "ADA_USDT", "AVAX_USDT", "LINK_USDT", "DOT_USDT"];

export default function QuickTrade({
  symbol,
  side,
  qty,
  onSymbolChange,
  onSideChange,
  onQtyChange,
  actionLoadingBtn,
  onAction,
  toast,
}: Props) {
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <Zap size={16} className="text-amber-500" />
          <h3 className="text-sm font-semibold">Hızlı İşlem</h3>
        </div>
        <select
          value={symbol}
          onChange={(e) => onSymbolChange(e.target.value)}
          className="rounded border border-border px-2 py-1.5 text-sm"
        >
          {SYMBOLS.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={side}
          onChange={(e) => onSideChange(e.target.value as "buy" | "sell")}
          className="rounded border border-border px-2 py-1.5 text-sm"
        >
          <option value="buy">AL (Long)</option>
          <option value="sell">SAT (Short)</option>
        </select>
        <input
          type="text"
          value={qty}
          onChange={(e) => onQtyChange(e.target.value)}
          className="w-20 rounded border border-border px-2 py-1.5 text-sm"
          placeholder="0.01"
        />
        <Button
          className={`text-sm ${side === "buy" ? "bg-primary" : "bg-danger"}`}
          onClick={() => {
            const parsed = parseFloat(qty);
            if (isNaN(parsed) || parsed <= 0) {
              toast("Geçerli bir miktar girin", "error");
              return;
            }
            onAction(
              () => manualPaperOrder(symbol, side, parsed),
              `${side === "buy" ? "AL" : "SAT"} ${symbol} ${parsed}`,
              "quick",
            );
          }}
          disabled={!!actionLoadingBtn}
        >
          <Plus size={14} /> {side === "buy" ? "AL" : "SAT"}
        </Button>
      </div>
    </Card>
  );
}
