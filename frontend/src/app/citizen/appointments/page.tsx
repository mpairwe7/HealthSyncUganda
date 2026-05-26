"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { ScopeNote } from "@/components/ui/scope-note";
import { useAuth } from "@/lib/store/auth";

export default function CitizenAppointmentsPage() {
  const session = useAuth((s) => s.session);
  const router = useRouter();
  useEffect(() => {
    if (!session) router.replace("/citizen/login");
  }, [session, router]);

  if (!session) return null;

  return (
    <ScopeNote
      title="Appointments"
      description="Book and manage upcoming visits at any facility."
      scopeBullets={[
        "Self-service booking by district, facility level, and service line.",
        "Calendar sync (ICS) for the citizen's device.",
        "Facility-side reschedule + cancel with audit trail.",
        "Queue-position feedback fed from the worker check-in flow.",
      ]}
      backHref="/citizen"
      backLabel="Back to citizen portal"
    />
  );
}
