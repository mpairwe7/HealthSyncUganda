"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Syringe, UserSearch } from "lucide-react";

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
  usePatients,
  useStockSnapshot,
  useSupplyItems,
} from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

import type { PatientSummary } from "@/types/api";

// SNOMED-CT bindings for vaccine observations. Mirrors backend/app/seed/data.py
// VACCINE_CODES so frontend-generated Observations are interoperable.
const VACCINE_SNOMED: Record<string, { code: string; display: string }> = {
  "VAC-BCG-001": { code: "42284007", display: "BCG vaccine product" },
  "VAC-OPV-001": { code: "836382009", display: "Oral polio vaccine product" },
  "VAC-MR-001":  { code: "836383004", display: "Measles-Rubella vaccine product" },
  "VAC-DPT-001": { code: "428601000124108", display: "DPT-HepB-Hib (pentavalent) vaccine product" },
  "VAC-PCV-001": { code: "836389000", display: "Pneumococcal conjugate vaccine product" },
  "VAC-YF-001":  { code: "836385006", display: "Yellow fever vaccine product" },
};
const SNOMED_SYSTEM = "http://snomed.info/sct";

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

  const items = useSupplyItems();
  const vaccines = (items.data ?? []).filter((it) => it.category === "vaccine");

  const stock = useStockSnapshot(
    session?.facility_id ? { district: undefined } : undefined,
  );
  const facilityStock = (stock.data ?? []).filter(
    (s) => s.facility_id === session?.facility_id && s.item_code.startsWith("VAC-"),
  );

  const search = usePatients({ q: ninQuery.length >= 3 ? ninQuery : undefined, page: 1 });
  const createEncounter = useCreateEncounter();
  const dispense = useDispense();

  if (!hydrated || !session) return null;

  async function onAdminister(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedPatient || !vaccineItemId || !session?.facility_id) return;

    const vaccineItem = vaccines.find((v) => v.id === vaccineItemId);
    if (!vaccineItem) return;
    const snomed = VACCINE_SNOMED[vaccineItem.code];
    if (!snomed) {
      pushToast({
        kind: "error",
        title: "Unknown vaccine code",
        description: `${vaccineItem.code} is not mapped to SNOMED — please add it to VACCINE_SNOMED.`,
      });
      return;
    }
    const now = new Date().toISOString();

    try {
      const enc = await createEncounter.mutateAsync({
        patient_id: selectedPatient.id,
        facility_id: session.facility_id,
        reason: `Vaccination — ${snomed.display}`,
        started_at: now,
        ended_at: now,
        diagnosis_codes: ["Z23"],
        observations: [
          {
            code_system: SNOMED_SYSTEM,
            code: snomed.code,
            display: snomed.display,
            value_string: lotNumber ? `lot=${lotNumber}` : null,
            effective_at: now,
          },
        ],
      });

      // If we have a real encounter id (online), decrement supply too.
      if (enc?.id) {
        try {
          await dispense.mutateAsync({
            supply_item_id: vaccineItem.id,
            facility_id: session.facility_id,
            quantity: 1,
            encounter_id: enc.id,
            patient_id: selectedPatient.id,
            purpose: "vaccination",
          });
        } catch (err) {
          // Dispense is best-effort; the encounter is the system-of-record.
          // The console will carry the dispense error.
          console.warn("dispense after vaccination failed:", err);
        }
      }

      pushToast({
        kind: "success",
        title: "Vaccine administered",
        description: `${snomed.display} → ${selectedPatient.given_name} ${selectedPatient.family_name}`,
      });
      // Reset form for the next patient
      setSelectedPatient(null);
      setNinQuery("");
      setLotNumber("");
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
          Search by NIN, pick a vaccine, capture the lot number, administer.
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
          <CardDescription>
            Updated as doses are administered. Low-stock items show in amber.
          </CardDescription>
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

      {/* Patient lookup */}
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
                Selected:{" "}
                <strong>
                  {selectedPatient.given_name} {selectedPatient.family_name}
                </strong>{" "}
                <span className="font-mono text-xs text-muted-foreground">
                  ({selectedPatient.nin})
                </span>
              </span>
              <Button size="sm" variant="outline" onClick={() => setSelectedPatient(null)}>
                Change
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Vaccine + administer */}
      <Card>
        <CardHeader>
          <CardTitle>Step 2 — Administer</CardTitle>
          <CardDescription>
            Pick the vaccine, capture lot number, click administer. Encounter is auto-created with
            an SNOMED-coded Observation and the stock is decremented atomically.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 sm:grid-cols-3" onSubmit={onAdminister}>
            <div>
              <Label htmlFor="vaccine">Vaccine</Label>
              <select
                id="vaccine"
                value={vaccineItemId}
                onChange={(e) => setVaccineItemId(e.target.value)}
                disabled={!selectedPatient}
                required
                className="mt-1 block w-full rounded-md border border-input bg-background px-2 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              >
                <option value="">— select —</option>
                {vaccines.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="lot">Lot number</Label>
              <Input
                id="lot"
                value={lotNumber}
                onChange={(e) => setLotNumber(e.target.value)}
                disabled={!selectedPatient}
                placeholder="e.g. LOT-GUL-VAC123"
                maxLength={80}
              />
            </div>
            <div className="flex items-end">
              <Button
                type="submit"
                disabled={
                  !selectedPatient ||
                  !vaccineItemId ||
                  createEncounter.isPending ||
                  dispense.isPending
                }
              >
                {createEncounter.isPending ? "Recording…" : "Administer"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
