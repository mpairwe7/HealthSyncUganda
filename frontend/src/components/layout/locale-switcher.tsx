"use client";

import { Languages } from "lucide-react";

import { LOCALES, type Locale } from "@/lib/i18n/dictionary";
import { useT } from "@/lib/i18n/provider";

export function LocaleSwitcher() {
  const { locale, setLocale, t } = useT();
  return (
    <label className="inline-flex items-center gap-1.5 text-sm" aria-label="Language">
      <Languages className="h-4 w-4 opacity-70" aria-hidden />
      <select
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        className="rounded-md border border-input bg-background px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {LOCALES.map((l) => (
          <option key={l} value={l}>
            {t.locales[l]}
          </option>
        ))}
      </select>
    </label>
  );
}
