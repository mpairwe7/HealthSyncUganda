"use client";

import { CloudOff } from "lucide-react";

import { useUi } from "@/lib/store/ui";

/**
 * Inline banner shown above primary content when the device reports it is
 * offline. The Header's <SyncIndicator> shows the same state globally; this
 * one is for in-page reassurance ("you're not seeing stale data because of
 * a bug — you're seeing stale data because the network dropped").
 *
 * Renders nothing when online to avoid layout shift on the common path.
 */
export function OfflineBanner({ note }: { note?: string }) {
  const online = useUi((s) => s.online);
  if (online) return null;
  return (
    <div className="flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
      <CloudOff className="h-4 w-4 shrink-0" aria-hidden />
      <span>{note ?? "Offline — showing the last synced data. Writes will queue."}</span>
    </div>
  );
}
