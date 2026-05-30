"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { AlertTriangle, CheckCircle2, Clock, Syringe, UserSearch } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import {
  useCreateEncounter,
  useDispense,
  useImmunisationStatus,
  usePatients,
  useStockSnapshot,
  useSupplyItems,
} from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

import type { AntigenStatusOut, PatientSummary } from "@/types/api";

const SNOMED_SYSTEM = "http://snomed.info/sct";

// Map supply_item.code → SNOMED. Mirrors backend/app/seed/data.py VACCINE_CODES.
const VACCINE_SNOMED: Record<string, { code: string; display: string }> = {
  "VAC-BCG-001": { code: "42284007", display: "BCG vaccine product" },
  "VAC-OPV-001": { code: "836382009", display: "Oral polio vaccine product" },
  "VAC-MR-001":  { code: "836383004", display: "Measles-Rubella vaccine product" },
  "VAC-DPT-001": { code: "428601000124108", display: "DPT-HepB-Hib (pentavalent) vaccine product" },
  "VAC-PCV-001": { code: "836389000", display: "Pneumococcal conjugate vaccine product" },
  "VAC-YF-001":  { code: "836385006", display: "Yellow fever vaccine product" },
};

function statusBadgeVariant(s: AntigenStatusOut["status"]) {
  switch (s) {
    case "complete":  return { variant: "success" as const, icon: CheckCircle2, label: "complete" };
    case "due":       return { variant: "default" as const, icon: Syringe,      label: "due now" };
    case "due-soon":  return { variant: "default" as const, icon: Clock,        label: "due soon" };
    case "overdue":   return { variant: "warning" as const, icon: AlertTriangle, label: "overdue" };
    case "not-yet":   return { variant: "default" as const, icon: Clock,        label: "not yet" };
  }
}

export default function WorkerImmunisationsPage() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();
  const pushToast = useUi((s) => s.pushToast);

  useEffect(() => {
    if (hydrated && !session) router.replace("/login");
  }, [hydrated, session, router]);

  const [ninQuery, setNinQuery] = useState("");
  const [selectedPatient, setSelectedPatient] = useState<PatientSummary | null>(null);
  const [vaccineItemId, setVaccineItemId] = useState<string>("");
  const [lotNumber, setLotNumber] = useState("");
  const [overrideBlock, setOverrideBlock] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");

  const items = useSupplyItems();
  const vaccines = (items.data ?? []).filter((it) => it.category === "vaccine");

  const stock = useStockSnapshot();
  const facilityStock = (stock.data ?? []).filter(
    (s) => s.facility_id === session?.facility_id && s.item_code.startsWith("VAC-"),
  );

  const search = usePatients({ q: ninQuery.length >= 3 ? ninQuery : undefined, page: 1 });
  const statusQ = useImmunisationStatus(selectedPatient?.id);
  const status = useMemo(() => statusQ.data ?? [], [statusQ.data]);

  const createEncounter = useCreateEncounter();
  const dispense = useDispense();

  // Map SNOMED → status to flag duplicates / advise nurses
  const statusByCode = useMemo(() => {
    const m = new Map<string, AntigenStatusOut>();
    for (const s of status) m.set(s.snomed_code, s);
    return m;
  }, [status]);

  function vaccineBlock(item: { code: string }): { blocked: boolean; reason?: string } {
    const snomed = VACCINE_SNOMED[item.code];
    if (!snomed) return { blocked: false };
    const s = statusByCode.get(snomed.code);
    if (!s) return { blocked: false };
    if (s.status === "complete") {
      return {
        blocked: true,
        reason: `Series already complete (${s.doses_given}/${s.series_size}). Last dose ${s.last_dose_at ? format(new Date(s.last_dose_at), "yyyy-MM-dd") : "?"}.`,
      };
    }
    if (s.next_due_date && new Date(s.next_due_date) > new Date()) {
      return {
        blocked: true,
        reason: `Next ${s.antigen}${s.next_dose_number} not due until ${s.next_due_date}.`,
      };
    }
    return { blocked: false };
  }

  const selectedVaccine = vaccines.find((v) => v.id === vaccineItemId);
  const selectedBlock = selectedVaccine ? vaccineBlock(selectedVaccine) : { blocked: false };

  if (!hydrated || !session) return null;

  async function onAdminister(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedPatient || !vaccineItemId || !session?.facility_id || !selectedVaccine) return;
    if (selectedBlock.blocked && !overrideBlock) {
      pushToast({
        kind: "warning",
        title: "Blocked by schedule",
        description: selectedBlock.reason ?? "Vaccine is not due.",
      });
      return;
    }
    const snomed = VACCINE_SNOMED[selectedVaccine.code];
    if (!snomed) {
      pushToast({
        kind: "error",
        title: "Unknown vaccine",
        description: `${selectedVaccine.code} is not mapped to SNOMED.`,
      });
      return;
    }
    const now = new Date().toISOString();
    const reasonNote = lotNumber ? `lot=${lotNumber}` : null;
    const overrideNote = overrideBlock ? `override=${overrideReason || "(no reason given)"}` : null;
    const valueString = [reasonNote, overrideNote].filter(Boolean).join("; ") || null;

    try {
      const enc = await createEncounter.mutateAsync({
        patient_id: selectedPatient.id,
        facility_id: session.facility_id,
        reason: `Vaccination — ${snomed.display}` + (overrideBlock ? " (override)" : ""),
        started_at: now,
        ended_at: now,
        diagnosis_codes: ["Z23"],
        observations: [
          {
            code_system: SNOMED_SYSTEM,
            code: snomed.code,
            display: snomed.display,
            value_string: valueString,
            effective_at: now,
          },
        ],
      });
      if (enc?.id) {
        try {
          await dispense.mutateAsync({
            supply_item_id: selectedVaccine.id,
            facility_id: session.facility_id,
            quantity: 1,
            encounter_id: enc.id,
            patient_id: selectedPatient.id,
            purpose: "vaccination",
          });
        } catch (err) {
          console.warn("dispense after vaccination failed:", err);
        }
      }
      pushToast({
        kind: "success",
        title: "Vaccine administered",
        description: `${snomed.display} → ${selectedPatient.given_name} ${selectedPatient.family_name}`,
      });
      // Reset
      setVaccineItemId("");
      setLotNumber("");
      setOverrideBlock(false);
      setOverrideReason("");
      // Refresh the status pane so the nurse immediately sees the new dose
      void statusQ.refetch();
    } catch (err) {
      pushToast({
        kind: "error",
        title: "Could not record vaccination",
        description: (err as Error).message,
      });
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Immunisations</h1>
        <p className="text-muted-foreground">
          Scan or type the NIN — the system computes who needs what against the UNEPI schedule and
          blocks duplicate doses.
        </p>
      </div>

      <OfflineBanner note="Offline — vaccinations queue locally and sync when the network returns." />

      {/* Facility stock summary */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Syringe className="h-5 w-5 text-primary" aria-hidden />
            <CardTitle>Vaccine stock at your facility</CardTitle>
          </div>
          <CardDescription>Low-stock items in amber. Refreshes as doses are administered.</CardDescription>
        </CardHeader>
        <CardContent>
          {stock.isLoading ? (
            <Skeleton className="h-24" />
          ) : facilityStock.length === 0 ? (
            <p className="text-sm text-muted-foreground">No vaccines stocked yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Vaccine</TableHead>
                  <TableHead className="text-right">On hand</TableHead>
                  <TableHead className="text-right">Reorder at</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {facilityStock.map((s) => (
                  <TableRow key={`${s.facility_id}-${s.item_code}`}>
                    <TableCell>{s.item_name}</TableCell>
                    <TableCell className="text-right font-mono">{s.on_hand}</TableCell>
                    <TableCell className="text-right font-mono">{s.reorder_threshold}</TableCell>
                    <TableCell>
                      <Badge variant={s.is_below_threshold ? "warning" : "success"}>
                        {s.is_below_threshold ? "low" : "ok"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Step 1 — Find the patient */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <UserSearch className="h-5 w-5 text-primary" aria-hidden />
            <CardTitle>Step 1 — Find the patient</CardTitle>
          </div>
          <CardDescription>Search by NIN, name, or phone (3+ characters).</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div>
            <Label htmlFor="nin-search">NIN or name</Label>
            <Input
              id="nin-search"
              value={ninQuery}
              onChange={(e) => {
                setNinQuery(e.target.value);
                setSelectedPatient(null);
              }}
              placeholder="CM85051712345X"
              maxLength={80}
              autoComplete="off"
            />
          </div>
          {search.isFetching && ninQuery.length >= 3 && <Skeleton className="h-16" />}
          {search.data && search.data.items.length > 0 && !selectedPatient && (
            <div className="rounded-md border">
              <Table>
                <TableBody>
                  {search.data.items.slice(0, 5).map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-mono text-xs">{p.nin}</TableCell>
                      <TableCell>
                        {p.given_name} {p.family_name}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{p.district}</TableCell>
                      <TableCell className="text-right">
                        <Button size="sm" variant="outline" onClick={() => setSelectedPatient(p)}>
                          Select
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
          {selectedPatient && (
            <div className="flex items-center justify-between rounded-md border bg-muted/50 px-3 py-2">
              <span>
                Selected: <strong>{selectedPatient.given_name} {selectedPatient.family_name}</strong>{" "}
                <span className="font-mono text-xs text-muted-foreground">({selectedPatient.nin})</span>
                <span className="ml-2 text-xs text-muted-foreground">
                  · {format(new Date(selectedPatient.birth_date), "yyyy-MM-dd")}
                </span>
              </span>
              <Button size="sm" variant="outline" onClick={() => {
                setSelectedPatient(null);
                setVaccineItemId("");
                setOverrideBlock(false);
              }}>
                Change
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Step 2 — Immunisation status (shown after a patient is picked) */}
      {selectedPatient && (
        <Card>
          <CardHeader>
            <CardTitle>Step 2 — Schedule status</CardTitle>
            <CardDescription>
              Computed against the UNEPI routine schedule. Overdue rows highlighted; complete rows show what&apos;s done.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {statusQ.isLoading ? (
              <Skeleton className="h-32" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Antigen</TableHead>
                    <TableHead>Doses</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Next due</TableHead>
                    <TableHead>Last dose</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {status.map((s) => {
                    const b = statusBadgeVariant(s.status);
                    const Icon = b.icon;
                    return (
                      <TableRow
                        key={s.antigen}
                        className={s.status === "overdue" ? "bg-amber-50" : undefined}
                      >
                        <TableCell>{s.display}</TableCell>
                        <TableCell className="font-mono">
                          {s.doses_given}/{s.series_size}
                        </TableCell>
                        <TableCell>
                          <Badge variant={b.variant} className="gap-1">
                            <Icon className="h-3 w-3" aria-hidden /> {b.label}
                          </Badge>
                          {s.overdue_days > 0 && (
                            <span className="ml-2 text-xs text-amber-900">
                              {s.overdue_days}d overdue
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-sm">
                          {s.next_due_date
                            ? format(new Date(s.next_due_date), "yyyy-MM-dd")
                            : "—"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {s.last_dose_at
                            ? format(new Date(s.last_dose_at), "yyyy-MM-dd")
                            : "never"}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}

      {/* Step 3 — Administer */}
      {selectedPatient && (
        <Card>
          <CardHeader>
            <CardTitle>Step 3 — Administer</CardTitle>
            <CardDescription>
              Pick a vaccine. Items already complete OR not yet due are blocked — use Override only with a
              clinical reason (e.g. catch-up campaign, MoH advisory).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-3 sm:grid-cols-3" onSubmit={onAdminister}>
              <div>
                <Label htmlFor="vaccine">Vaccine</Label>
                <select
                  id="vaccine"
                  value={vaccineItemId}
                  onChange={(e) => {
                    setVaccineItemId(e.target.value);
                    setOverrideBlock(false);
                    setOverrideReason("");
                  }}
                  required
                  className="mt-1 block w-full rounded-md border border-input bg-background px-2 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="">— select —</option>
                  {vaccines.map((v) => {
                    const b = vaccineBlock(v);
                    return (
                      <option key={v.id} value={v.id}>
                        {v.name}
                        {b.blocked ? "  — blocked" : ""}
                      </option>
                    );
                  })}
                </select>
                {selectedBlock.blocked && (
                  <p className="mt-1 text-xs text-amber-900">{selectedBlock.reason}</p>
                )}
              </div>
              <div>
                <Label htmlFor="lot">Lot number</Label>
                <Input
                  id="lot"
                  value={lotNumber}
                  onChange={(e) => setLotNumber(e.target.value)}
                  placeholder="e.g. LOT-GUL-VAC123"
                  maxLength={80}
                />
              </div>
              <div className="flex items-end">
                <Button
                  type="submit"
                  disabled={!vaccineItemId || createEncounter.isPending || dispense.isPending}
                >
                  {createEncounter.isPending ? "Recording…" : "Administer"}
                </Button>
              </div>

              {selectedBlock.blocked && (
                <div className="sm:col-span-3 rounded-md border border-amber-300 bg-amber-50 p-3">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={overrideBlock}
                      onChange={(e) => setOverrideBlock(e.target.checked)}
                      className="h-4 w-4 accent-amber-700"
                    />
                    <span>Override block (clinical decision)</span>
                  </label>
                  {overrideBlock && (
                    <Input
                      className="mt-2"
                      value={overrideReason}
                      onChange={(e) => setOverrideReason(e.target.value)}
                      placeholder="Reason (recorded in audit log)"
                      maxLength={200}
                    />
                  )}
                </div>
              )}
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
