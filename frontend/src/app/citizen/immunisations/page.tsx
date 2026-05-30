"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { Syringe } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useFacilities, useMyImmunisations } from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

export default function CitizenImmunisationsPage() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();
  const online = useUi((s) => s.online);

  useEffect(() => {
    if (hydrated && !session) router.replace("/citizen/login");
  }, [hydrated, session, router]);

  const immunisations = useMyImmunisations(!!session);
  const facilities = useFacilities();
  const facilityById = new Map((facilities.data ?? []).map((f) => [f.id, f]));

  if (!hydrated || !session) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Immunisations</h1>
        <p className="text-muted-foreground">
          Vaccines you have received at any facility, oldest at the bottom.
        </p>
      </div>

      {!online && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Offline — showing the last synced copy of your record.
        </div>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Syringe className="h-5 w-5 text-primary" aria-hidden />
            <CardTitle>Vaccination history</CardTitle>
          </div>
          <CardDescription>
            Sourced from FHIR Observations across every facility on the network.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {immunisations.isLoading ? (
            <Skeleton className="h-32" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Vaccine</TableHead>
                  <TableHead>Facility</TableHead>
                  <TableHead className="text-right">Code</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(immunisations.data ?? []).map((imm) => {
                  const fac = imm.facility_id
                    ? facilityById.get(imm.facility_id)
                    : undefined;
                  return (
                    <TableRow key={imm.id}>
                      <TableCell>
                        {format(new Date(imm.administered_at), "yyyy-MM-dd")}
                      </TableCell>
                      <TableCell>{imm.display ?? imm.code}</TableCell>
                      <TableCell>
                        {fac ? `${fac.name} · ${fac.district}` : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Badge variant="default" className="font-mono text-xs">
                          {imm.code}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {(immunisations.data ?? []).length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={4}
                      className="py-8 text-center text-sm text-muted-foreground"
                    >
                      No vaccinations on record yet. Visit any facility and the
                      vaccine will appear here within minutes.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
