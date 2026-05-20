"use client";

import { useEffect } from "react";

/**
 * Tiny client component you can drop into a route's `layout.tsx` to enable
 * the service worker. Kept opt-in so dev hot-reloads aren't intercepted.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    if (process.env.NODE_ENV !== "production") return;
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }, []);
  return null;
}
