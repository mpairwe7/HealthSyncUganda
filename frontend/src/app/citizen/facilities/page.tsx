"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { ScopeNote } from "@/components/ui/scope-note";
import { useAuth } from "@/lib/store/auth";

export default function CitizenFacilitiesPage() {
  const session = useAuth((s) => s.session);
  const router = useRouter();
  useEffect(() => {
    if (!session) router.replace("/citizen/login");
  }, [session, router]);

  if (!session) return null;

  return (
    <ScopeNote
      title="Find a facility"
      description="Locate the nearest accredited health centre, with directions."
      scopeBullets={[
        "Map view of facilities (MoH master list) filtered by district + level.",
        "Walk/drive directions via OpenStreetMap (no Google dependency).",
        "Service availability + opening hours surfaced from each facility's record.",
        "Offline-first: the most recent facility list is cached on the device.",
      ]}
      backHref="/citizen"
      backLabel="Back to citizen portal"
    />
  );
}
