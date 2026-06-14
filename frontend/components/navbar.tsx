"use client";

import { useState, useEffect } from "react";
import {
  Activity,
  BarChart3,
  Beaker,
  BookOpen,
  Database,
  LineChart,
  LayoutDashboard,
  Menu,
  PieChart,
  Play,
  Shield,
  X,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/paper-trading", label: "Paper Trading", icon: Play },
  { href: "/portfolio", label: "Portföy", icon: PieChart },
  { href: "/strategy-research", label: "Araştırma Lab", icon: Beaker },
  { href: "/strategy-health", label: "Strateji Sağlık", icon: Shield },
  { href: "/market-regime", label: "Piyasa Rejimi", icon: Activity },
  { href: "/execution-quality", label: "İcra Kalitesi", icon: Zap },
  { href: "/data-quality", label: "Veri Kalitesi", icon: Database },
  { href: "/backtests", label: "Backtest", icon: LineChart },
  { href: "/walk-forward", label: "Walk-Forward", icon: BarChart3 },
  { href: "/learning", label: "Otomatik Öğrenme", icon: BookOpen },
] as const;

export function Navbar() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <>
      {/* Mobile hamburger */}
      <button
        className="fixed left-4 top-4 z-50 flex h-10 w-10 items-center justify-center rounded-md border border-border bg-white shadow-sm lg:hidden"
        onClick={() => setMobileOpen(!mobileOpen)}
        aria-label={mobileOpen ? "Menüyü kapat" : "Menüyü aç"}
        aria-expanded={mobileOpen}
        aria-controls="sidebar-nav"
      >
        {mobileOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      {/* Overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        id="sidebar-nav"
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-56 flex-col border-r border-border bg-white transition-transform duration-200",
          "lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
        aria-label="Ana navigasyon"
      >
        {/* Logo */}
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-white">
            G
          </div>
          <span className="text-sm font-semibold leading-tight">
            Gate.io
            <br />
            <span className="text-xs font-normal text-muted">Capital Bot</span>
          </span>
        </div>

        {/* Links */}
        <nav className="flex-1 overflow-y-auto px-3 py-3" aria-label="Sayfa bağlantıları">
          {NAV_ITEMS.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "mb-0.5 flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition",
                  active
                    ? "bg-primary/10 font-medium text-primary"
                    : "text-muted hover:bg-border/60 hover:text-foreground",
                )}
                aria-current={active ? "page" : undefined}
              >
                <item.icon size={16} aria-hidden="true" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="border-t border-border px-4 py-3">
          <p className="text-xs text-muted">v0.1.0 · Sermaye Koruma</p>
        </div>
      </aside>
    </>
  );
}
