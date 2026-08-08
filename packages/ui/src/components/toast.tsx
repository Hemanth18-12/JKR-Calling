"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import * as React from "react";

import { cn } from "../utils";

type ToastVariant = "default" | "success" | "danger";

interface Toast {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  toast: (t: Omit<Toast, "id">) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

const ICONS: Record<ToastVariant, React.ReactNode> = {
  default: <Info className="h-4 w-4 text-primary" />,
  success: <CheckCircle2 className="h-4 w-4 text-success" />,
  danger: <AlertCircle className="h-4 w-4 text-danger" />,
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);

  const toast = React.useCallback((t: Omit<Toast, "id">) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { ...t, id }]);
    setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), 5000);
  }, []);

  const dismiss = (id: string) => setToasts((prev) => prev.filter((x) => x.id !== id));

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex w-full max-w-sm flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              "flex items-start gap-3 rounded-md border border-border bg-surface-raised p-4 shadow-lg animate-in slide-in-from-bottom-2",
              t.variant === "danger" && "border-danger/40",
              t.variant === "success" && "border-success/40"
            )}
          >
            {ICONS[t.variant]}
            <div className="flex-1 space-y-0.5">
              <p className="text-sm font-medium text-foreground">{t.title}</p>
              {t.description ? <p className="text-xs text-muted-foreground">{t.description}</p> : null}
            </div>
            <button onClick={() => dismiss(t.id)} aria-label="Dismiss" className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}
