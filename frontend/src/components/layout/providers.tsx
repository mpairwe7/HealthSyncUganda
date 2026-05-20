"use client";

import { useEffect, useState } from "react";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";

import { makeQueryClient } from "@/lib/api/query-client";
import { idbPersister } from "@/lib/api/persister";
import { startDrainer } from "@/lib/offline/drainer";
import { useUi } from "@/lib/store/ui";
import { I18nProvider } from "@/lib/i18n/provider";
import { Toaster } from "@/components/ui/toaster";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => makeQueryClient());
  const setOnline = useUi((s) => s.setOnline);

  useEffect(() => {
    function onlineHandler() {
      setOnline(true);
    }
    function offlineHandler() {
      setOnline(false);
    }
    window.addEventListener("online", onlineHandler);
    window.addEventListener("offline", offlineHandler);
    setOnline(navigator.onLine);
    startDrainer();
    return () => {
      window.removeEventListener("online", onlineHandler);
      window.removeEventListener("offline", offlineHandler);
    };
  }, [setOnline]);

  return (
    <I18nProvider>
      <PersistQueryClientProvider
        client={client}
        persistOptions={{
          persister: idbPersister,
          maxAge: 7 * 24 * 60 * 60 * 1_000,
          buster: "v1",
        }}
      >
        {children}
        <Toaster />
      </PersistQueryClientProvider>
    </I18nProvider>
  );
}
