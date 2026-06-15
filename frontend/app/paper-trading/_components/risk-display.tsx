"use client";

import { ShieldAlert } from "lucide-react";

import { Card } from "@/components/ui/card";
import type { PaperRiskStatus } from "@/types/paper";

interface Props {
  risk: PaperRiskStatus | null;
}

export default function RiskDisplay({ risk }: Props) {
  return (
    <Card>
      <div className="mb-4 flex items-center gap-2">
        <ShieldAlert size={17} />
        <h2 className="text-base font-semibold">Risk Durumu</h2>
      </div>
      {risk ? (
        <div className="space-y-5">
          <RiskItem label="Günlük Zarar" current={risk.current_daily_loss_pct * 100} max={risk.max_daily_loss_pct * 100} unit="%" color={risk.max_daily_loss_pct > 0 && risk.current_daily_loss_pct / risk.max_daily_loss_pct > 0.7 ? "#b42318" : "#146c5d"} />
          <RiskItem label="Drawdown" current={risk.current_drawdown * 100} max={risk.max_drawdown_pct * 100} unit="%" color={risk.max_drawdown_pct > 0 && risk.current_drawdown / risk.max_drawdown_pct > 0.7 ? "#b42318" : "#146c5d"} />
          <RiskItem label="Exposure" current={risk.current_exposure * 100} max={risk.max_exposure_pct * 100} unit="%" color={risk.max_exposure_pct > 0 && risk.current_exposure / risk.max_exposure_pct > 0.7 ? "#b42318" : "#146c5d"} />
          <RiskItem label="Açık Pozisyon" current={risk.current_open_positions} max={risk.max_open_positions} unit="" color={risk.current_open_positions >= risk.max_open_positions ? "#b42318" : "#146c5d"} />
        </div>
      ) : (
        <p className="text-sm text-muted">Risk verisi yok.</p>
      )}
    </Card>
  );
}

function RiskItem({ label, current, max, unit, color }: { label: string; current: number; max: number; unit: string; color: string }) {
  const pct = max > 0 ? Math.min((current / max) * 100, 100) : 0;
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-sm">
        <span className="text-muted">{label}</span>
        <span className="font-medium">
          {current.toFixed(unit === "%" ? 2 : 0)}{unit} / {max.toFixed(unit === "%" ? 2 : 0)}{unit}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-border">
        <div className="h-2 rounded-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}
