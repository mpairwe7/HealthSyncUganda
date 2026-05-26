"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { ScopeNote } from "@/components/ui/scope-note";
import { useAuth } from "@/lib/store/auth";

export default function CitizenImmunisationsPage() {
  const session = useAuth((s) => s.session);
  const router = useRouter();
  useEffect(() => {
    if (!session) router.replace("/citizen/login");
  }, [session, router]);

  if (!session) return null;

  return (
    <ScopeNote
      title="Immunisations"
      description="Vaccines you've received and reminders for upcoming doses."
      scopeBullets={[
        "Lifetime immunisation history pulled from every facility you've visited.",
        "Reminders for due/overdue vaccines aligned to UNEPI's schedule.",
        "DPI-stamped vaccination cards downloadable as FHIR-bundle PDFs.",
        "SMS/USSD nudges via Africa's Talking when the citizen device is offline.",
      ]}
      backHref="/citizen"
      backLabel="Back to citizen portal"
    />
  );
}
