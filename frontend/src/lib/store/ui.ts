/**
 * Lightweight UI store — toast queue, online/offline indicator, sync count.
 */

import { create } from "zustand";

export type ToastKind = "info" | "success" | "warning" | "error";

export type Toast = {
  id: string;
  kind: ToastKind;
  title: string;
  description?: string;
  durationMs?: number;
};

type State = {
  online: boolean;
  pendingSyncCount: number;
  toasts: Toast[];

  setOnline: (online: boolean) => void;
  setPendingSyncCount: (n: number) => void;
  pushToast: (t: Omit<Toast, "id">) => void;
  dismissToast: (id: string) => void;
};

export const useUi = create<State>((set) => ({
  online: typeof navigator !== "undefined" ? navigator.onLine : true,
  pendingSyncCount: 0,
  toasts: [],
  setOnline: (online) => set({ online }),
  setPendingSyncCount: (n) => set({ pendingSyncCount: n }),
  pushToast: (t) =>
    set((s) => ({
      toasts: [
        ...s.toasts,
        { ...t, id: Math.random().toString(36).slice(2) },
      ],
    })),
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((x) => x.id !== id) })),
}));
