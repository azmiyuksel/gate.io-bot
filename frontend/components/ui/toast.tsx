"use client";

import { AlertCircle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

type ToastType = "success" | "error" | "info" | "warning";

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextIdRef = useRef(0);

  const toast = useCallback((message: string, type: ToastType = "info") => {
    const id = ++nextIdRef.current;
    setToasts((prev) => [...prev, { id, message, type }]);
  }, []);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} onRemove={() => remove(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ toast, onRemove }: { toast: ToastItem; onRemove: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onRemove, 4000);
    return () => clearTimeout(timer);
  }, [onRemove]);

  const icons = {
    success: <CheckCircle2 size={16} className="text-green-600" />,
    error: <XCircle size={16} className="text-danger" />,
    warning: <AlertCircle size={16} className="text-amber-600" />,
    info: <Info size={16} className="text-blue-600" />,
  };

  const borders = {
    success: "border-green-200 bg-green-50",
    error: "border-red-200 bg-red-50",
    warning: "border-amber-200 bg-amber-50",
    info: "border-blue-200 bg-blue-50",
  };

  return (
    <div
      className={cn(
        "pointer-events-auto flex items-center gap-3 rounded-md border px-4 py-3 text-sm shadow-lg transition-all animate-slide-in-right",
        borders[toast.type],
      )}
      role="alert"
    >
      {icons[toast.type]}
      <span className="flex-1">{toast.message}</span>
      <button onClick={onRemove} className="text-muted hover:text-foreground" aria-label="Kapat">
        <X size={14} />
      </button>
    </div>
  );
}
