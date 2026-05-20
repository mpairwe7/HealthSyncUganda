"use client";

import { useEffect } from "react";
import { CheckCircle2, AlertTriangle, Info, XCircle, X } from "lucide-react";
import { useUi, type Toast } from "@/lib/store/ui";
import { cn } from "@/lib/utils/cn";

const iconForKind = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

const colorForKind = {
  info: "border-blue-300 bg-blue-50 text-blue-900",
  success: "border-emerald-300 bg-emerald-50 text-emerald-900",
  warning: "border-amber-300 bg-amber-50 text-amber-900",
  error: "border-red-300 bg-red-50 text-red-900",
};

function ToastItem({ toast }: { toast: Toast }) {
  const dismiss = useUi((s) => s.dismissToast);
  const Icon = iconForKind[toast.kind];

  useEffect(() => {
    const id = setTimeout(() => dismiss(toast.id), toast.durationMs ?? 5000);
    return () => clearTimeout(id);
  }, [dismiss, toast.id, toast.durationMs]);

  return (
    <div
      className={cn(
        "pointer-events-auto flex items-start gap-3 rounded-md border px-4 py-3 shadow-md",
        colorForKind[toast.kind],
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{toast.title}</p>
        {toast.description && (
          <p className="text-sm opacity-80 mt-0.5">{toast.description}</p>
        )}
      </div>
      <button
        type="button"
        onClick={() => dismiss(toast.id)}
        className="opacity-60 hover:opacity-100"
        aria-label="Dismiss"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export function Toaster() {
  const toasts = useUi((s) => s.toasts);
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:items-end">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} />
      ))}
    </div>
  );
}
