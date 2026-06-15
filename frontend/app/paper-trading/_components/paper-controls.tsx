"use client";

import { CirclePause, Play, RotateCcw, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  pausePaperTrading,
  resumePaperTrading,
  startPaperTrading,
  stopPaperTrading,
} from "@/lib/paper-api";

type ActionFn = (fn: () => Promise<boolean>, successMsg: string, btnId?: string) => Promise<void>;

interface Shortcut {
  key: string;
  label: string;
  when: string;
}

interface Props {
  botStatus: string;
  actionLoadingBtn: string;
  onAction: ActionFn;
  onResetClick: () => void;
  shortcuts: Shortcut[];
}

export default function PaperControls({
  botStatus,
  actionLoadingBtn,
  onAction,
  onResetClick,
  shortcuts,
}: Props) {
  return (
    <>
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-2 px-6 pb-4">
        {botStatus === "STOPPED" && (
          <Button onClick={() => onAction(() => startPaperTrading(), "Paper trading başlatıldı", "start")} disabled={!!actionLoadingBtn}>
            <Play size={15} /> Başlat [S]
          </Button>
        )}
        {botStatus === "RUNNING" && (
          <>
            <Button onClick={() => onAction(() => pausePaperTrading(), "Duraklatıldı", "pause")} disabled={!!actionLoadingBtn} className="bg-amber-600">
              <CirclePause size={15} /> Duraklat [P]
            </Button>
            <Button onClick={() => onAction(() => stopPaperTrading(), "Durduruldu", "stop")} disabled={!!actionLoadingBtn} className="bg-danger">
              <Square size={15} /> Durdur [X]
            </Button>
          </>
        )}
        {botStatus === "PAUSED" && (
          <>
            <Button onClick={() => onAction(() => resumePaperTrading(), "Devam ediliyor", "resume")} disabled={!!actionLoadingBtn}>
              <Play size={15} /> Devam Et [R]
            </Button>
            <Button onClick={() => onAction(() => stopPaperTrading(), "Durduruldu", "stop")} disabled={!!actionLoadingBtn} className="bg-danger">
              <Square size={15} /> Durdur [X]
            </Button>
          </>
        )}
        <Button onClick={onResetClick} disabled={!!actionLoadingBtn} className="bg-foreground/80">
          <RotateCcw size={15} /> Sıfırla
        </Button>
      </div>
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-1 px-6 pb-3">
        <span className="text-xs text-muted">Kısayollar:</span>
        {shortcuts.map((s) => (
          <kbd key={s.key} className="rounded border border-border bg-gray-50 px-1.5 py-0.5 text-xs text-muted">
            {s.key}
          </kbd>
        ))}
      </div>
    </>
  );
}
