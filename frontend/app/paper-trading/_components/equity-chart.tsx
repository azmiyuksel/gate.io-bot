"use client";

import { BarChart3 } from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/card";
import { money } from "@/lib/utils";

interface Props {
  equityChartData: { time: string; equity: number }[];
  dailyPnlData: { date: string; pnl: number }[];
  rollingSharpe: number;
}

export default function EquityChart({ equityChartData, dailyPnlData, rollingSharpe }: Props) {
  return (
    <section className="mx-auto grid max-w-7xl gap-5 lg:grid-cols-[2fr_1fr]">
      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">Equity Curve</h2>
          <span className="text-sm text-muted">
            Sharpe (rolling) {rollingSharpe.toFixed(2)}
          </span>
        </div>
        <div className="h-72">
          {equityChartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={equityChartData}>
                <CartesianGrid stroke="#ecece7" />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
                <Tooltip formatter={(v: number) => `$${money(v)}`} />
                <Area type="monotone" dataKey="equity" stroke="#146c5d" fill="#146c5d33" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted">Equity verisi yok.</div>
          )}
        </div>
      </Card>

      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">Günlük PnL</h2>
          <BarChart3 size={16} className="text-muted" />
        </div>
        <div className="h-72">
          {dailyPnlData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dailyPnlData}>
                <CartesianGrid stroke="#ecece7" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v: number) => `$${v.toFixed(2)}`} />
                <Bar dataKey="pnl" radius={[4, 4, 0, 0]}>
                  {dailyPnlData.map((entry, i) => (
                    <Cell key={i} fill={entry.pnl >= 0 ? "#146c5d" : "#b42318"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-muted">İşlem verisi yok.</div>
          )}
        </div>
      </Card>
    </section>
  );
}
