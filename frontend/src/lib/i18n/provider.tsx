"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { dictionaries, type Locale, LOCALES } from "@/lib/i18n/dictionary";

const STORAGE_KEY = "healthsync.locale";
const DEFAULT_LOCALE: Locale = "en";

type Ctx = {
  locale: Locale;
  t: typeof dictionaries.en;
  setLocale: (l: Locale) => void;
};

const I18nCtx = createContext<Ctx | null>(null);

function readPreferred(): Locale {
  if (typeof window === "undefined") return DEFAULT_LOCALE;
  const stored = window.localStorage.getItem(STORAGE_KEY) as Locale | null;
  if (stored && (LOCALES as string[]).includes(stored)) return stored;
  // Browser hint — only honour known locales
  const nav = (window.navigator?.language ?? "").toLowerCase();
  if (nav.startsWith("lg")) return "lg";
  return DEFAULT_LOCALE;
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  // Hydration-safe: resolve preferred locale only on the client.
  useEffect(() => {
    setLocaleState(readPreferred());
  }, []);

  const setLocale = (l: Locale) => {
    setLocaleState(l);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, l);
      document.documentElement.lang = l;
    }
  };

  // Keep the <html lang="…"> attribute honest for screen readers / search.
  useEffect(() => {
    if (typeof document !== "undefined") document.documentElement.lang = locale;
  }, [locale]);

  return (
    <I18nCtx.Provider value={{ locale, t: dictionaries[locale], setLocale }}>
      {children}
    </I18nCtx.Provider>
  );
}

export function useT() {
  const ctx = useContext(I18nCtx);
  if (!ctx) throw new Error("useT must be used inside <I18nProvider>");
  return ctx;
}
