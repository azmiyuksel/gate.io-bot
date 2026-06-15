"use client";

import { Activity } from "lucide-react";

import { Card } from "@/components/ui/card";
import { fmtUTC } from "@/lib/utils";
import type { PaperSignalDiagnostics } from "@/types/paper";

interface Props {
  diagnostics: PaperSignalDiagnostics | null;
  maxReasonCount: number;
}

export default function SignalDiagnostics({ diagnostics, maxReasonCount }: Props) {
  return (
    <section className="mx-auto grid max-w-7xl gap-5 px-6 pb-6 lg:grid-cols-[1fr_1fr]">
      <Card>
        <div className="mb-1 flex items-center gap-2">
          <Activity size={17} />
          <h2 className="text-base font-semibold">Sinyal Tanılama</h2>
        </div>
        <p className="mb-2 text-sm text-muted">
          Son {diagnostics?.window_hours ?? 24} saatte girişlerin neden atlandığı
          {diagnostics ? ` (${diagnostics.evaluations} değerlendirme)` : ""}.
        </p>
        {diagnostics && diagnostics.evaluations === 0 && (
          <div className="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">
            Hiç değerlendirme kaydı yok. <strong>paper-worker</strong> servisi
            çalışmıyor olabilir veya worker dış ağa (Gate.io) erişemiyor olabilir.
            <code className="ml-1">docker compose logs -f paper-worker</code> ile kontrol edin.
          </div>
        )}
        {diagnostics?.last_evaluation_at && (
          <p className="mb-4 text-xs text-muted">
            Son değerlendirme:{" "}
            {fmtUTC(diagnostics.last_evaluation_at, true)}
          </p>
        )}
        {diagnostics && Object.keys(diagnostics.reason_counts).length > 0 ? (
          <div className="space-y-2">
            {Object.entries(diagnostics.reason_counts).map(([reason, count]) => {
              const pct = (count / maxReasonCount) * 100;
              const approved = reason.startsWith("approved") || reason.startsWith("long_entry") || reason.startsWith("short_entry");
              return (
                <div key={reason}>
                  <div className="flex items-center justify-between text-sm">
                    <span className={approved ? "font-medium text-primary" : ""}>{reason}</span>
                    <span className="text-muted">{count}</span>
                  </div>
                  <div className="mt-1 h-1.5 w-full rounded bg-border">
                    <div
                      className={`h-1.5 rounded ${approved ? "bg-primary" : "bg-amber-600"}`}
                      style={{ width: `${Math.round(pct)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-muted">Henüz değerlendirme kaydı yok.</p>
        )}
      </Card>

      <Card>
        <h2 className="mb-4 text-base font-semibold">Sembol Bazında Son Durum</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border text-muted">
              <tr>
                <th className="py-2" scope="col">Sembol</th>
                <th scope="col">Son Neden</th>
                <th scope="col">Zaman</th>
              </tr>
            </thead>
            <tbody>
              {diagnostics && Object.keys(diagnostics.latest_by_symbol).length > 0 ? (
                Object.entries(diagnostics.latest_by_symbol).map(([symbol, info]) => (
                  <tr key={symbol} className="border-b border-border">
                    <td className="py-3 font-medium">{symbol}</td>
                    <td className={info.reason.includes("entry") || info.reason === "approved" ? "text-primary font-medium" : "text-muted"}>
                      {info.reason}
                    </td>
                    <td className="text-xs text-muted">{info.at ? fmtUTC(info.at, true) : "-"}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td className="py-6 text-muted" colSpan={3}>Kayıt yok.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </section>
  );
}
