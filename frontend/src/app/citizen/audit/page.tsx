"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { ScopeNote } from "@/components/ui/scope-note";
import { useAuth } from "@/lib/store/auth";

export default function CitizenAuditPage() {
  const session = useAuth((s) => s.session);
  const router = useRouter();
  useEffect(() => {
    if (!session) router.replace("/citizen/login");
  }, [session, router]);

  if (!session) return null;

  return (
    <ScopeNote
      title="Access history"
      description="Who has looked at your record, when, and under what consent."
      scopeBullets={[
        "Per-actor view of every read on your record (worker, facility, purpose, timestamp).",
        "Filter by date, facility, or consent identifier.",
        "Reverse-chronological feed backed by the append-only audit log.",
        "Export your access history as a signed PDF for personal records.",
      ]}
      backHref="/citizen"
      backLabel="Back to citizen portal"
    />
  );
}
