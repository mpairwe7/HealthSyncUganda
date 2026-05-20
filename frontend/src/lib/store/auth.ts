/**
 * Zustand store for the current session. Persisted to sessionStorage so a
 * browser refresh doesn't drop the active token, but a tab close does
 * (defensive default for a health-data app).
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type Role =
  | "citizen"
  | "worker"
  | "pharmacist"
  | "district_admin"
  | "ministry_admin";

export type Session = {
  token: string;
  role: Role;
  subject: string;
  name: string | null;
  facility_id: string | null;
  expiresAt: number;
};

type State = {
  session: Session | null;
  setSession: (s: Session | null) => void;
  isAuthenticated: () => boolean;
};

export const useAuth = create<State>()(
  persist(
    (set, get) => ({
      session: null,
      setSession: (session) => {
        set({ session });
        if (typeof window !== "undefined") {
          if (session) {
            window.sessionStorage.setItem("healthsync.token", session.token);
          } else {
            window.sessionStorage.removeItem("healthsync.token");
          }
        }
      },
      isAuthenticated: () => {
        const s = get().session;
        return !!s && s.expiresAt > Date.now();
      },
    }),
    {
      name: "healthsync.auth",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);
