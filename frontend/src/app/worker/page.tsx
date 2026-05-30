"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  Activity,
  ClipboardPlus,
  Package,
  Search,
  Stethoscope,
  Syringe,
  UserCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { OfflineBanner } from "@/components/ui/offline-banner";
import { Skeleton } from "@/components/ui/skeleton";
import { useEncountersByFacility, useStockSnapshot } from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";

export default function WorkerHome() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();
  useEffect(() => {
    if (hydrated && !session) router.replace("/login");
  }, [hydrated, session, router]);

  const lowStock = useStockSnapshot({ only_below_threshold: true });
  const today = useEncountersByFacility(
    {
      facility_id: session?.facility_id ?? undefined,
      since_days: 1,
    },
    !!session?.facility_id,
  );
  const last30 = useEncountersByFacility(
    {
      facility_id: session?.facility_id ?? undefined,
      since_days: 30,
    },
    !!session?.facility_id,
  );

  if (!hydrated || !session) return null;

  const todayRow = (today.data ?? [])[0];
  const last30Row = (last30.data ?? [])[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Worker dashboard</h1>
        <p className="text-muted-foreground">
          {session.name ?? session.subject} · {session.role.replace("_", " ")}
        </p>
      </div>

      <OfflineBanner />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {/* This facility today + last-30d card — only meaningful when a facility is set */}
        {session.facility_id && (
          <Card className="lg:col-span-2 border-emerald-300 bg-emerald-50">
            <CardHeader>
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-emerald-900" aria-hidden />
                <CardTitle className="text-emerald-900">This facility</CardTitle>
              </div>
              <CardDescription className="text-emerald-900/80">
                {todayRow?.facility_name ?? last30Row?.facility_name ?? "Your facility"} · live counts.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {today.isLoading || last30.isLoading ? (
                <Skeleton className="h-12" />
              ) : (
                <div className="grid grid-cols-2 gap-6 text-emerald-900">
                  <Stat
                    label="Encounters today"
                    value={todayRow?.encounter_count ?? 0}
                    sub={`${todayRow?.patient_count ?? 0} distinct patients`}
                  />
                  <Stat
                    label="Encounters · last 30 days"
                    value={last30Row?.encounter_count ?? 0}
                    sub={`${last30Row?.patient_count ?? 0} distinct patients`}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {lowStock.data && lowStock.data.length > 0 && (
          <Card className="border-amber-300 bg-amber-50">
            <CardHeader>
              <CardTitle className="text-amber-900">
                {lowStock.data.length} items below reorder threshold
              </CardTitle>
              <CardDescription className="text-amber-800">
                Click any item to inspect and initiate a transfer.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Link href="/worker/supply">
                <Button variant="outline">Open supply</Button>
              </Link>
            </CardContent>
          </Card>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Tile
          icon={<Search className="h-5 w-5 text-primary" />}
          title="Find patient"
          description="Search by NIN, name, or phone."
          href="/worker/patients"
        />
        <Tile
          icon={<ClipboardPlus className="h-5 w-5 text-primary" />}
          title="Enrol patient"
          description="Register a new citizen. Works offline."
          href="/worker/patients/new"
        />
        <Tile
          icon={<Stethoscope className="h-5 w-5 text-primary" />}
          title="Record encounter"
          description="Vitals, diagnoses, prescriptions."
          href="/worker/patients"
        />
        <Tile
          icon={<Syringe className="h-5 w-5 text-primary" />}
          title="Immunisations"
          description="Scan NIN, pick antigen, administer."
          href="/worker/immunisations"
        />
        <Tile
          icon={<Package className="h-5 w-5 text-primary" />}
          title="Supply"
          description="Stock, batches, transfers, dispense."
          href="/worker/supply"
        />
        <Tile
          icon={<UserCircle className="h-5 w-5 text-primary" />}
          title="My profile"
          description="Role, facility, session, sign out."
          href="/worker/profile"
        />
      </div>
    </div>
  );
}

function Tile({
  icon,
  title,
  description,
  href,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  href: string;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {icon}
          <CardTitle className="text-base">{title}</CardTitle>
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <Link href={href}>
          <Button variant="outline" className="w-full">
            Open
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, sub }: { label: string; value: number; sub: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide opacity-80">{label}</div>
      <div className="text-3xl font-bold">{value}</div>
      <div className="text-xs opacity-80">{sub}</div>
    </div>
  );
}
