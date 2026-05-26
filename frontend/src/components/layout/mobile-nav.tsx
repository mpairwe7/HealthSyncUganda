"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { LogOut, Menu, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useT } from "@/lib/i18n/provider";
import { useAuth } from "@/lib/store/auth";
import { cn } from "@/lib/utils/cn";

type NavLabelKey = "citizenRecords" | "workerDashboard" | "administration";

interface NavItem {
  href: string;
  labelKey: NavLabelKey;
  roles: string[];
}

interface Props {
  items: NavItem[];
}

/**
 * MobileNav — hamburger button + slide-down sheet for small viewports.
 *
 * Hidden at sm+ (the Header renders inline links there). At <sm it is the
 * only way to navigate between citizen / worker / admin sections.
 *
 * The sheet also surfaces user name + sign-out and the active route so
 * users don't have to guess where they are after deep-linking.
 */
export function MobileNav({ items }: Props) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const session = useAuth((s) => s.session);
  const setSession = useAuth((s) => s.setSession);
  const { t } = useT();
  const sheetId = useId();

  // Close on route change.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // Close on Escape.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Prevent body scroll while sheet is open.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const visibleItems = session ? items.filter((n) => n.roles.includes(session.role)) : [];

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        aria-controls={sheetId}
        className="sm:hidden"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <X className="h-5 w-5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
      </Button>

      {/* Backdrop — clicking it closes the sheet */}
      {open && (
        <button
          type="button"
          aria-label="Close menu"
          tabIndex={-1}
          className="fixed inset-0 top-14 z-30 bg-black/40 sm:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Sheet — slides down from below the header */}
      <div
        id={sheetId}
        role="dialog"
        aria-modal={open}
        aria-label="Main navigation"
        className={cn(
          "fixed left-0 right-0 top-14 z-40 origin-top border-b bg-background shadow-lg transition-all sm:hidden",
          open
            ? "max-h-[calc(100dvh-3.5rem)] overflow-y-auto opacity-100"
            : "pointer-events-none max-h-0 opacity-0",
        )}
      >
        <nav className="container flex flex-col gap-1 py-3">
          {session && (
            <div className="mb-2 rounded-md bg-muted/50 px-3 py-2 text-sm">
              <div className="font-medium">{session.name ?? session.subject}</div>
              <div className="text-xs text-muted-foreground capitalize">
                {session.role.replace("_", " ")}
                {session.facility_id && " · " + session.subject.slice(-6)}
              </div>
            </div>
          )}

          {visibleItems.length === 0 ? (
            <Link
              href="/login"
              className="rounded-md px-3 py-3 text-base hover:bg-accent"
              onClick={() => setOpen(false)}
            >
              Sign in
            </Link>
          ) : (
            visibleItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-md px-3 py-3 text-base transition-colors hover:bg-accent",
                  pathname.startsWith(item.href) && "bg-accent text-accent-foreground",
                )}
                onClick={() => setOpen(false)}
              >
                {t.nav[item.labelKey]}
              </Link>
            ))
          )}

          {session && (
            <Button
              variant="outline"
              className="mt-2 w-full justify-start"
              onClick={() => {
                setSession(null);
                setOpen(false);
              }}
            >
              <LogOut className="mr-2 h-4 w-4" aria-hidden />
              {t.nav.signOut}
            </Button>
          )}
        </nav>
      </div>
    </>
  );
}
