"use client";

import { useEffect, useState } from "react";
import { Cloud, CloudOff, RefreshCw } from "lucide-react";

import { drainQueue } from "@/lib/offline/drainer";
import { listPending, subscribe as subscribePending } from "@/lib/offline/queue";
import { useUi } from "@/lib/store/ui";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils/cn";

export function SyncIndicator() {
  const online = useUi((s) => s.online);
  const [count, setCount] = useState(0);
  const [draining, setDraining] = useState(false);

  useEffect(() => {
    const refresh = async () => setCount((await listPending()).length);
    void refresh();
    return subscribePending(refresh);
  }, []);

  async function handleSync() {
    setDraining(true);
    try {
      await drainQueue();
    } finally {
      setDraining(false);
      setCount((await listPending()).length);
    }
  }

  return (
    <button
      onClick={handleSync}
      disabled={draining}
      className={cn(
        "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
        online
          ? "bg-emerald-50 text-emerald-900 hover:bg-emerald-100"
          : "bg-amber-100 text-amber-900 hover:bg-amber-200",
      )}
      aria-label={online ? "Sync now" : "Offline — sync queued"}
    >
      {online ? (
        draining ? (
          <RefreshCw className="h-4 w-4 animate-spin" />
        ) : (
          <Cloud className="h-4 w-4" />
        )
      ) : (
        <CloudOff className="h-4 w-4" />
      )}
      <span className="hidden sm:inline">{online ? "Online" : "Offline"}</span>
      {count > 0 && (
        <Badge variant={online ? "default" : "warning"}>{count} pending</Badge>
      )}
    </button>
  );
}
