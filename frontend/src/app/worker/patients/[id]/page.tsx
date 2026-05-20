"use client";

import { use, useState } from "react";
import { format } from "date-fns";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useCreateEncounter,
  useEncountersByPatient,
  usePatient,
} from "@/lib/api/hooks";
import { useAuth } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

export default function PatientDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const patient = usePatient(id);
  const encounters = useEncountersByPatient(id);
  const session = useAuth((s) => s.session);
  const pushToast = useUi((s) => s.pushToast);
  const create = useCreateEncounter();

  const [reason, setReason] = useState("");
  const [temperature, setTemperature] = useState("");
  const [bp, setBp] = useState("");
  const [diagnosis, setDiagnosis] = useState("");

  async function recordEncounter() {
    if (!session || !patient.data) return;
    const now = new Date().toISOString();
    await create.mutateAsync({
      patient_id: patient.data.id,
      facility_id: session.facility_id ?? "",
      reason,
      started_at: now,
      ended_at: now,
      diagnosis_codes: diagnosis ? [diagnosis] : [],
      observations: [
        temperature
          ? {
              code_system: "http://loinc.org",
              code: "8310-5",
              display: "Body temperature",
              value_quantity: parseFloat(temperature),
              value_unit: "Cel",
              effective_at: now,
            }
          : null,
        bp
          ? {
              code_system: "http://loinc.org",
              code: "55284-4",
              display: "Blood pressure",
              value_string: bp,
              effective_at: now,
            }
          : null,
      ].filter(Boolean) as never,
    });
    setReason("");
    setTemperature("");
    setBp("");
    setDiagnosis("");
    pushToast({ kind: "success", title: "Encounter saved" });
  }

  if (patient.isLoading) return <Skeleton className="h-64" />;
  if (!patient.data) return <p>Patient not found.</p>;
  const p = patient.data;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {p.given_name} {p.family_name}
          </h1>
          <p className="text-muted-foreground">
            <span className="font-mono">{p.nin}</span> · {p.gender} ·{" "}
            {format(new Date(p.birth_date), "yyyy-MM-dd")} · {p.district}
          </p>
        </div>
        <Badge variant={p.deceased ? "destructive" : "success"}>
          {p.deceased ? "Deceased" : "Active"}
        </Badge>
      </div>

      <Tabs defaultValue="encounters" className="space-y-4">
        <TabsList>
          <TabsTrigger value="encounters">Encounters</TabsTrigger>
          <TabsTrigger value="record">Record new</TabsTrigger>
          <TabsTrigger value="identity">Identity</TabsTrigger>
        </TabsList>

        <TabsContent value="encounters">
          <Card>
            <CardHeader>
              <CardTitle>History</CardTitle>
              <CardDescription>All encounters across all facilities.</CardDescription>
            </CardHeader>
            <CardContent>
              {encounters.isLoading ? (
                <Skeleton className="h-32" />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Date</TableHead>
                      <TableHead>Reason</TableHead>
                      <TableHead>Diagnoses</TableHead>
                      <TableHead>Observations</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(encounters.data ?? []).map((enc) => (
                      <TableRow key={enc.id}>
                        <TableCell>{format(new Date(enc.started_at), "yyyy-MM-dd HH:mm")}</TableCell>
                        <TableCell>{enc.reason}</TableCell>
                        <TableCell>{enc.diagnosis_codes.join(", ") || "—"}</TableCell>
                        <TableCell className="text-xs">
                          {enc.observations
                            .map(
                              (o) =>
                                `${o.display ?? o.code}: ${
                                  o.value_string ??
                                  (o.value_quantity != null
                                    ? `${o.value_quantity}${o.value_unit ?? ""}`
                                    : "—")
                                }`,
                            )
                            .join(" · ")}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="record">
          <Card>
            <CardHeader>
              <CardTitle>Record encounter</CardTitle>
              <CardDescription>
                Works offline — entries queue and sync when network returns.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Reason for visit</Label>
                <Input
                  value={reason}
                  placeholder="e.g. Antenatal visit"
                  onChange={(e) => setReason(e.target.value)}
                />
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>Temperature (°C)</Label>
                  <Input
                    type="number"
                    step="0.1"
                    value={temperature}
                    onChange={(e) => setTemperature(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Blood pressure (sys/dia)</Label>
                  <Input
                    placeholder="120/80"
                    value={bp}
                    onChange={(e) => setBp(e.target.value)}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label>ICD-10 diagnosis code</Label>
                <Input
                  placeholder="B54"
                  value={diagnosis}
                  onChange={(e) => setDiagnosis(e.target.value.toUpperCase())}
                />
              </div>
              <Button
                onClick={recordEncounter}
                disabled={create.isPending || !reason}
                className="w-full sm:w-auto"
              >
                Save encounter
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="identity">
          <Card>
            <CardContent className="pt-6">
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <Field label="NIN" value={p.nin} mono />
                <Field label="Phone" value={p.phone ?? "—"} />
                <Field label="Email" value={p.email ?? "—"} />
                <Field label="District" value={p.district} />
                <Field label="Sub-county" value={p.sub_county ?? "—"} />
                <Field label="Parish" value={p.parish ?? "—"} />
                <Field label="Village" value={p.village ?? "—"} />
                <Field label="Record version" value={String(p.record_version)} />
              </dl>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
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
