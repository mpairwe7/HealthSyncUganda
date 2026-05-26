"use client";

import { use, useState } from "react";
import { format } from "date-fns";
import { AlertCircle, PlusCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { OfflineBanner } from "@/components/ui/offline-banner";
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
  useAddObservation,
  useCreateEncounter,
  useEncountersByPatient,
  useFamily,
  useLinkCaregiver,
  useMarkDeceased,
  usePatient,
  useUnlinkCaregiver,
} from "@/lib/api/hooks";
import { LOINC_SYSTEM, VITAL_CODES } from "@/lib/clinical/loinc";
import { useAuth } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

import type { CaregiverRelationship, ObservationIn } from "@/types/api";

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
  const markDeceased = useMarkDeceased();

  // Encounter form state — now covers all standard vitals
  const [reason, setReason] = useState("");
  const [temperature, setTemperature] = useState("");
  const [bp, setBp] = useState("");
  const [weight, setWeight] = useState("");
  const [height, setHeight] = useState("");
  const [pulse, setPulse] = useState("");
  const [oxygen, setOxygen] = useState("");
  const [respiratory, setRespiratory] = useState("");
  const [diagnosis, setDiagnosis] = useState("");

  // Inline confirm state for deceased flag
  const [confirmDeceased, setConfirmDeceased] = useState(false);
  const [deceasedPurpose, setDeceasedPurpose] = useState("Death certificate filed");

  // Caregiver-link form state
  const family = useFamily(id);
  const linkCaregiver = useLinkCaregiver(id);
  const unlinkCaregiver = useUnlinkCaregiver(id);
  const [caregiverNin, setCaregiverNin] = useState("");
  const [caregiverRel, setCaregiverRel] = useState<CaregiverRelationship>("guardian");

  // Add-observation panel state
  const [appendEncounterId, setAppendEncounterId] = useState<string>("");
  const [appendCode, setAppendCode] = useState<keyof typeof VITAL_CODES>("TEMPERATURE");
  const [appendValue, setAppendValue] = useState("");
  const addObs = useAddObservation(appendEncounterId || undefined);

  function buildVital(key: keyof typeof VITAL_CODES, raw: string): ObservationIn | null {
    if (!raw) return null;
    const def = VITAL_CODES[key];
    const now = new Date().toISOString();
    if (def.kind === "quantity") {
      const v = parseFloat(raw);
      if (Number.isNaN(v)) return null;
      return {
        code_system: LOINC_SYSTEM,
        code: def.code,
        display: def.display,
        value_quantity: v,
        value_unit: def.unit ?? null,
        effective_at: now,
      };
    }
    return {
      code_system: LOINC_SYSTEM,
      code: def.code,
      display: def.display,
      value_string: raw,
      effective_at: now,
    };
  }

  async function recordEncounter() {
    if (!session || !patient.data) return;
    const now = new Date().toISOString();
    const observations = [
      buildVital("TEMPERATURE", temperature),
      buildVital("BLOOD_PRESSURE", bp),
      buildVital("WEIGHT", weight),
      buildVital("HEIGHT", height),
      buildVital("PULSE", pulse),
      buildVital("OXYGEN_SAT", oxygen),
      buildVital("RESPIRATORY_RATE", respiratory),
    ].filter((o): o is ObservationIn => o !== null);

    await create.mutateAsync({
      patient_id: patient.data.id,
      facility_id: session.facility_id ?? "",
      reason,
      started_at: now,
      ended_at: now,
      diagnosis_codes: diagnosis ? [diagnosis] : [],
      observations,
    });
    setReason("");
    setTemperature("");
    setBp("");
    setWeight("");
    setHeight("");
    setPulse("");
    setOxygen("");
    setRespiratory("");
    setDiagnosis("");
    pushToast({ kind: "success", title: "Encounter saved", description: `${observations.length} observations recorded.` });
  }

  async function appendObservation() {
    if (!appendEncounterId || !appendValue) return;
    const o = buildVital(appendCode, appendValue);
    if (!o) return;
    try {
      await addObs.mutateAsync([o]);
      setAppendValue("");
    } catch (err) {
      pushToast({
        kind: "error",
        title: "Could not append observation",
        description: (err as Error).message,
      });
    }
  }

  async function doMarkDeceased(value: boolean) {
    if (!patient.data) return;
    try {
      await markDeceased.mutateAsync({
        patientId: patient.data.id,
        body: { deceased: value, purpose: value ? deceasedPurpose : "Flag cleared" },
      });
      setConfirmDeceased(false);
    } catch (err) {
      pushToast({
        kind: "error",
        title: "Could not update vital status",
        description: (err as Error).message,
      });
    }
  }

  if (patient.isLoading) return <Skeleton className="h-64" />;
  if (!patient.data) return <p>Patient not found.</p>;
  const p = patient.data;

  return (
    <div className="space-y-6">
      <OfflineBanner />

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
          <TabsTrigger value="append">Add observation</TabsTrigger>
          <TabsTrigger value="family">Family</TabsTrigger>
          <TabsTrigger value="identity">Identity</TabsTrigger>
          <TabsTrigger value="admin">Admin</TabsTrigger>
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
                    {(encounters.data ?? []).length === 0 && (
                      <TableRow>
                        <TableCell colSpan={4} className="py-6 text-center text-muted-foreground">
                          No encounters yet — use the &quot;Record new&quot; tab.
                        </TableCell>
                      </TableRow>
                    )}
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
                Works offline — entries queue and sync when network returns. Empty vitals are
                skipped; every captured value is LOINC-coded.
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
                <VitalInput
                  label="Temperature (°C)"
                  hint={VITAL_CODES.TEMPERATURE.hint}
                  type="number"
                  step="0.1"
                  min={VITAL_CODES.TEMPERATURE.min}
                  max={VITAL_CODES.TEMPERATURE.max}
                  value={temperature}
                  onChange={setTemperature}
                />
                <VitalInput
                  label="Blood pressure (sys/dia)"
                  hint={VITAL_CODES.BLOOD_PRESSURE.hint}
                  placeholder="120/80"
                  value={bp}
                  onChange={setBp}
                />
                <VitalInput
                  label="Weight (kg)"
                  type="number"
                  step="0.1"
                  min={VITAL_CODES.WEIGHT.min}
                  max={VITAL_CODES.WEIGHT.max}
                  value={weight}
                  onChange={setWeight}
                />
                <VitalInput
                  label="Height (cm)"
                  type="number"
                  step="0.1"
                  min={VITAL_CODES.HEIGHT.min}
                  max={VITAL_CODES.HEIGHT.max}
                  value={height}
                  onChange={setHeight}
                />
                <VitalInput
                  label="Pulse (/min)"
                  type="number"
                  min={VITAL_CODES.PULSE.min}
                  max={VITAL_CODES.PULSE.max}
                  value={pulse}
                  onChange={setPulse}
                />
                <VitalInput
                  label="Oxygen saturation (%)"
                  type="number"
                  min={VITAL_CODES.OXYGEN_SAT.min}
                  max={VITAL_CODES.OXYGEN_SAT.max}
                  value={oxygen}
                  onChange={setOxygen}
                />
                <VitalInput
                  label="Respiratory rate (/min)"
                  type="number"
                  min={VITAL_CODES.RESPIRATORY_RATE.min}
                  max={VITAL_CODES.RESPIRATORY_RATE.max}
                  value={respiratory}
                  onChange={setRespiratory}
                />
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
                {create.isPending ? "Saving…" : "Save encounter"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="append">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <PlusCircle className="h-5 w-5 text-primary" aria-hidden />
                <CardTitle>Append observation to an existing encounter</CardTitle>
              </div>
              <CardDescription>
                Use this when a late-arriving result (lab value, follow-up vital) belongs to an
                already-recorded visit. The encounter row stays — only its observations grow.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-3 sm:grid-cols-4">
                <div className="sm:col-span-2">
                  <Label>Encounter</Label>
                  <select
                    value={appendEncounterId}
                    onChange={(e) => setAppendEncounterId(e.target.value)}
                    className="mt-1 block w-full rounded-md border border-input bg-background px-2 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <option value="">— select —</option>
                    {(encounters.data ?? []).map((enc) => (
                      <option key={enc.id} value={enc.id}>
                        {format(new Date(enc.started_at), "yyyy-MM-dd")} — {enc.reason}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label>Vital</Label>
                  <select
                    value={appendCode}
                    onChange={(e) => setAppendCode(e.target.value as keyof typeof VITAL_CODES)}
                    className="mt-1 block w-full rounded-md border border-input bg-background px-2 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {Object.entries(VITAL_CODES).map(([key, def]) => (
                      <option key={key} value={key}>
                        {def.display}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label>Value</Label>
                  <Input
                    value={appendValue}
                    onChange={(e) => setAppendValue(e.target.value)}
                    placeholder={
                      VITAL_CODES[appendCode].kind === "string"
                        ? "120/80"
                        : VITAL_CODES[appendCode].unit ?? ""
                    }
                  />
                </div>
                <div className="sm:col-span-4 flex justify-end">
                  <Button
                    onClick={appendObservation}
                    disabled={!appendEncounterId || !appendValue || addObs.isPending}
                  >
                    {addObs.isPending ? "Adding…" : "Append observation"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="family">
          <Card>
            <CardHeader>
              <CardTitle>Family</CardTitle>
              <CardDescription>
                Caregivers linked to this patient. Mothers / fathers / guardians can see this
                patient&apos;s record from <strong>their</strong> citizen portal once linked. Useful
                when one parent brings multiple children to the clinic in one visit.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {family.isLoading ? (
                <Skeleton className="h-20" />
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>NIN</TableHead>
                      <TableHead>Relationship</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(family.data ?? []).map((m) => (
                      <TableRow key={m.link_id}>
                        <TableCell>
                          {m.given_name} {m.family_name}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{m.nin}</TableCell>
                        <TableCell className="capitalize">{m.relationship}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => unlinkCaregiver.mutate(m.link_id)}
                            disabled={unlinkCaregiver.isPending}
                          >
                            Unlink
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                    {(family.data ?? []).length === 0 && (
                      <TableRow>
                        <TableCell
                          colSpan={4}
                          className="py-6 text-center text-sm text-muted-foreground"
                        >
                          No caregivers linked yet.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              )}

              <div className="rounded-md border bg-muted/40 p-3">
                <div className="mb-2 text-sm font-semibold">Link a caregiver</div>
                <form
                  className="grid gap-3 sm:grid-cols-[2fr,1fr,auto]"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!caregiverNin) return;
                    linkCaregiver.mutate(
                      {
                        caregiver_nin: caregiverNin.toUpperCase(),
                        relationship: caregiverRel,
                      },
                      {
                        onSuccess: () => {
                          setCaregiverNin("");
                          setCaregiverRel("guardian");
                        },
                      },
                    );
                  }}
                >
                  <div>
                    <Label>Caregiver NIN</Label>
                    <Input
                      value={caregiverNin}
                      onChange={(e) => setCaregiverNin(e.target.value)}
                      placeholder="CM85051712345X"
                      maxLength={14}
                      minLength={14}
                      required
                      className="font-mono"
                    />
                  </div>
                  <div>
                    <Label>Relationship</Label>
                    <select
                      value={caregiverRel}
                      onChange={(e) => setCaregiverRel(e.target.value as CaregiverRelationship)}
                      className="mt-1 block w-full rounded-md border border-input bg-background px-2 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <option value="mother">Mother</option>
                      <option value="father">Father</option>
                      <option value="guardian">Guardian</option>
                      <option value="grandparent">Grandparent</option>
                      <option value="sibling">Sibling</option>
                      <option value="aunt">Aunt</option>
                      <option value="uncle">Uncle</option>
                      <option value="other">Other</option>
                    </select>
                  </div>
                  <div className="flex items-end">
                    <Button type="submit" disabled={linkCaregiver.isPending}>
                      {linkCaregiver.isPending ? "Linking…" : "Link"}
                    </Button>
                  </div>
                </form>
                <p className="mt-2 text-xs text-muted-foreground">
                  The caregiver must already be enrolled. If not, register them first under{" "}
                  <strong>Enrol patient</strong>.
                </p>
              </div>
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

        <TabsContent value="admin">
          <Card className={p.deceased ? "border-destructive/40" : "border-amber-300"}>
            <CardHeader>
              <div className="flex items-center gap-2">
                <AlertCircle className="h-5 w-5 text-amber-900" aria-hidden />
                <CardTitle className="text-amber-900">Vital status</CardTitle>
              </div>
              <CardDescription>
                Marks the patient as deceased — preserves encounter history but locks future writes
                in workflows that respect the flag. Reversible.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {!p.deceased && !confirmDeceased && (
                <Button variant="destructive" onClick={() => setConfirmDeceased(true)}>
                  Mark as deceased…
                </Button>
              )}
              {!p.deceased && confirmDeceased && (
                <div className="space-y-3 rounded-md border border-destructive/40 bg-destructive/5 p-3">
                  <Label>Reason / source</Label>
                  <Input
                    value={deceasedPurpose}
                    onChange={(e) => setDeceasedPurpose(e.target.value)}
                    maxLength={300}
                  />
                  <div className="flex gap-2">
                    <Button
                      variant="destructive"
                      onClick={() => doMarkDeceased(true)}
                      disabled={markDeceased.isPending}
                    >
                      {markDeceased.isPending ? "Saving…" : "Confirm"}
                    </Button>
                    <Button variant="outline" onClick={() => setConfirmDeceased(false)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
              {p.deceased && (
                <Button
                  variant="outline"
                  onClick={() => doMarkDeceased(false)}
                  disabled={markDeceased.isPending}
                >
                  Clear deceased flag (record correction)
                </Button>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

type VitalInputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> & {
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
};

function VitalInput({ label, hint, value, onChange, ...rest }: VitalInputProps) {
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      <Input {...rest} value={value} onChange={(e) => onChange(e.target.value)} />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
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
