"use client";

import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Onayla",
  cancelLabel = "İptal",
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="fixed inset-0 bg-black/40" onClick={onCancel} aria-hidden="true" />
      <div className="relative z-10 mx-4 w-full max-w-md rounded-lg border border-border bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-full ${danger ? "bg-red-100" : "bg-amber-100"}`}>
            <AlertTriangle size={20} className={danger ? "text-danger" : "text-amber-600"} />
          </div>
          <h2 id="confirm-title" className="text-lg font-semibold">{title}</h2>
        </div>
        <p className="mb-6 text-sm text-muted">{message}</p>
        <div className="flex justify-end gap-3">
          <Button className="bg-transparent text-foreground hover:bg-border/60" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button className={danger ? "bg-danger" : ""} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
