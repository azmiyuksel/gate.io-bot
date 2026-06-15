import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function money(value: number | string) {
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * Format a price with magnitude-aware precision, so sub-dollar coins (DOGE, XLM,
 * ...) and small ticks don't collapse to "0.00".
 */
export function fmtPrice(value: number | string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "0.00";
  const abs = Math.abs(n);
  const max = abs >= 1000 ? 2 : abs >= 1 ? 4 : abs >= 0.01 ? 6 : 8;
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: max });
}

/**
 * Format a (crypto) quantity with up to 8 decimals, trimming trailing zeros, so
 * fractional sizes like 0.00021 BTC aren't shown as "0.00".
 */
export function fmtQty(value: number | string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return "0";
  return n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 8 });
}

/** Compact UTC label for chart axes: "dd/mm HH:mm" (no suffix). */
export function fmtUTCShort(value: string | number | Date): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString("en-GB", {
    timeZone: "UTC",
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/**
 * Format an ISO timestamp in UTC with an explicit "UTC" suffix. Exchange data is
 * UTC; rendering in the browser's local zone (unlabelled) misleads traders about
 * when trades/signals actually happened.
 */
export function fmtUTC(value: string | number | Date, withSeconds = false): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "-";
  const s = d.toLocaleString("en-GB", {
    timeZone: "UTC",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}),
    hour12: false,
  });
  return `${s} UTC`;
}

export function num(v: string | number | null | undefined): number {
  if (v === null || v === undefined) return 0;
  return typeof v === "number" ? v : Number(v);
}
