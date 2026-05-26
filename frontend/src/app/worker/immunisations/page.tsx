"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { ScopeNote } from "@/components/ui/scope-note";
import { useAuth } from "@/lib/store/auth";

export default function WorkerImmunisationsPage() {
  const session = useAuth((s) => s.session);
  const router = useRouter();
  useEffect(() => {
    if (!session) router.replace("/login");
  }, [session, router]);

  if (!session) return null;

  return (
    <ScopeNote
      title="Immunisations"
      description="Children and adolescents due for vaccines at this facility."
      scopeBullets={[
        "Facility-scoped list of upcoming, due, and overdue doses per UNEPI's schedule.",
        "Mass-administration workflow: scan NIN, batch-confirm, capture lot + expiry.",
        "Auto-emit FHIR Immunization resources + DHIS2 weekly aggregate counts.",
        "Stock decrement linked to the supply ledger (atomic with the dispense).",
      ]}
      backHref="/worker"
      backLabel="Back to worker dashboard"
    />
  );
}
