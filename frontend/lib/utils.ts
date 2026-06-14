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
