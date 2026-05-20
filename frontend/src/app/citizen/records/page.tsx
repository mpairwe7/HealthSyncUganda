"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEncountersByPatient, usePatients } from "@/lib/api/hooks";
import { useAuth } from "@/lib/store/auth";

export default function CitizenRecordsPage() {
  const session = useAuth((s) => s.session);
  const router = useRouter();

  useEffect(() => {
    if (!session) router.replace("/citizen/login");
  }, [session, router]);

  // Citizens log in with their NIN — we look up their patient record by NIN.
  const search = usePatients({ q: session?.subject, page: 1 });
  const patient = search.data?.items[0];
  const encounters = useEncountersByPatient(patient?.id);

  if (!session) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">My records</h1>
        <p className="text-muted-foreground">
          Read-only view across every facility you&apos;ve visited.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Identity</CardTitle>
          <CardDescription>Sourced from NIRA & the National Patient Index.</CardDescription>
        </CardHeader>
        <CardContent>
          {search.isLoading ? (
            <Skeleton className="h-24" />
          ) : patient ? (
            <dl className="grid gap-2 text-sm sm:grid-cols-2">
              <Field label="NIN" value={patient.nin} mono />
              <Field label="Full name" value={`${patient.given_name} ${patient.family_name}`} />
              <Field label="Gender" value={patient.gender} />
              <Field label="Date of birth" value={patient.birth_date} />
              <Field label="District" value={patient.district} />
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">
              No patient record found for your NIN yet. Visit a facility to be enrolled.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Encounter history</CardTitle>
          <CardDescription>Chronological list of clinical visits.</CardDescription>
        </CardHeader>
        <CardContent>
          {encounters.isLoading ? (
            <Skeleton className="h-40" />
          ) : encounters.data && encounters.data.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Diagnoses</TableHead>
                  <TableHead>Observations</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {encounters.data.map((enc) => (
                  <TableRow key={enc.id}>
                    <TableCell>{format(new Date(enc.started_at), "yyyy-MM-dd")}</TableCell>
                    <TableCell className="max-w-[200px] truncate">{enc.reason}</TableCell>
                    <TableCell>
                      <Badge variant={enc.status === "finished" ? "success" : "secondary"}>
                        {enc.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{enc.diagnosis_codes.join(", ") || "—"}</TableCell>
                    <TableCell className="text-xs">
                      {enc.observations.length > 0
                        ? enc.observations
                            .map((o) => o.display ?? o.code)
                            .slice(0, 3)
                            .join(", ")
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No encounters on file yet.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={mono ? "font-mono" : ""}>{value}</dd>
    </div>
  );
}
