"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, LogOut } from "lucide-react";

import { LocaleSwitcher } from "@/components/layout/locale-switcher";
import { SyncIndicator } from "@/components/offline/sync-indicator";
import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n/provider";
import { useAuth } from "@/lib/store/auth";
import { cn } from "@/lib/utils/cn";

const navItems = [
  { href: "/citizen", labelKey: "citizenRecords" as const, roles: ["citizen"] },
  { href: "/worker", labelKey: "workerDashboard" as const, roles: ["worker", "pharmacist"] },
  { href: "/admin", labelKey: "administration" as const, roles: ["district_admin", "ministry_admin"] },
];

export function Header() {
  const session = useAuth((s) => s.session);
  const setSession = useAuth((s) => s.setSession);
  const pathname = usePathname();
  const { t } = useT();

  const visibleNav = session
    ? navItems.filter((n) => n.roles.includes(session.role))
    : [];

  return (
    <header className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur">
      <div className="container flex h-14 items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <Activity className="h-5 w-5 text-primary" />
          <span>HealthSync</span>
          <span className="hidden text-muted-foreground sm:inline">Uganda</span>
        </Link>
        <nav className="hidden sm:flex items-center gap-1 text-sm">
          {visibleNav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "rounded-md px-3 py-1.5 transition-colors hover:bg-accent",
                pathname.startsWith(item.href) && "bg-accent text-accent-foreground",
              )}
            >
              {t.nav[item.labelKey]}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <LocaleSwitcher />
          <SyncIndicator />
          {session && (
            <>
              <span className="hidden text-sm text-muted-foreground md:inline">
                {session.name ?? session.subject}
              </span>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t.nav.signOut}
                onClick={() => setSession(null)}
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
