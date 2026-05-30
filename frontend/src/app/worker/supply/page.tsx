"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { AlertTriangle, ArrowRightLeft, PackagePlus, PillBottle, Send } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { OfflineBanner } from "@/components/ui/offline-banner";
import { Select } from "@/components/ui/select";
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
  useDispense,
  useFacilities,
  useStockSnapshot,
  useStockTransfer,
  useSupplyItems,
} from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

export default function SupplyPage() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();
  useEffect(() => {
    if (hydrated && !session) router.replace("/login");
  }, [hydrated, session, router]);

  const [district, setDistrict] = useState<string | "">("");
  const snapshot = useStockSnapshot({ district: district || undefined });
  const items = useSupplyItems();
  const facilities = useFacilities();
  const transfer = useStockTransfer();
  const dispense = useDispense();
  const pushToast = useUi((s) => s.pushToast);

  const [tFrom, setTFrom] = useState("");
  const [tTo, setTTo] = useState("");
  const [tItem, setTItem] = useState("");
  const [tQty, setTQty] = useState(50);
  const [tReason, setTReason] = useState("Replenishment");

  const [dItem, setDItem] = useState("");
  const [dQty, setDQty] = useState(1);
  const [dPurpose, setDPurpose] = useState("medication-dispense");

  const districts = useMemo(
    () => Array.from(new Set((facilities.data ?? []).map((f) => f.district))).sort(),
    [facilities.data],
  );

  async function doTransfer() {
    try {
      await transfer.mutateAsync({
        from_facility_id: tFrom,
        to_facility_id: tTo,
        supply_item_id: tItem,
        quantity: tQty,
        reason: tReason,
      });
      pushToast({ kind: "success", title: "Transfer completed" });
    } catch (err) {
      pushToast({
        kind: "error",
        title: "Transfer failed",
        description: (err as Error).message,
      });
    }
  }

  async function doDispense() {
    if (!session?.facility_id) {
      pushToast({
        kind: "error",
        title: "No facility on session",
        description: "Dispense requires a worker assigned to a facility.",
      });
      return;
    }
    try {
      await dispense.mutateAsync({
        supply_item_id: dItem,
        facility_id: session.facility_id,
        quantity: dQty,
        purpose: dPurpose,
      });
    } catch (err) {
      pushToast({
        kind: "error",
        title: "Dispense failed",
        description: (err as Error).message,
      });
    }
  }

  if (!hydrated || !session) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Supply</h1>
          <p className="text-muted-foreground">Live facility-level stock with low-stock alerts.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/worker/supply/receive">
            <Button variant="outline" size="sm">
              <PackagePlus className="mr-1.5 h-4 w-4" aria-hidden />
              Receive stock
            </Button>
          </Link>
          <Link href="/worker/supply/transfers">
            <Button variant="outline" size="sm">
              <Send className="mr-1.5 h-4 w-4" aria-hidden />
              Transfer history
            </Button>
          </Link>
        </div>
      </div>

      <OfflineBanner />


      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Stock snapshot</CardTitle>
            <CardDescription>Filter by district. Below-threshold rows highlighted.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Label className="text-sm">District</Label>
              <Select
                value={district}
                onChange={(e) => setDistrict(e.target.value)}
                className="max-w-xs"
              >
                <option value="">All districts</option>
                {districts.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </Select>
            </div>
            {snapshot.isLoading ? (
              <Skeleton className="h-48" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Facility</TableHead>
                    <TableHead>Item</TableHead>
                    <TableHead className="text-right">On-hand</TableHead>
                    <TableHead className="text-right">Reorder at</TableHead>
                    <TableHead>Earliest expiry</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(snapshot.data ?? []).map((row) => (
                    <TableRow
                      key={`${row.facility_id}-${row.item_code}`}
                      className={row.is_below_threshold ? "bg-amber-50" : undefined}
                    >
                      <TableCell className="font-medium">{row.facility_name}</TableCell>
                      <TableCell>{row.item_name}</TableCell>
                      <TableCell className="text-right">{row.on_hand}</TableCell>
                      <TableCell className="text-right">{row.reorder_threshold}</TableCell>
                      <TableCell>
                        {row.earliest_expiry
                          ? format(new Date(row.earliest_expiry), "yyyy-MM-dd")
                          : "—"}
                      </TableCell>
                      <TableCell>
                        {row.is_below_threshold ? (
                          <Badge variant="warning" className="gap-1">
                            <AlertTriangle className="h-3 w-3" /> Low
                          </Badge>
                        ) : (
                          <Badge variant="success">OK</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ArrowRightLeft className="h-4 w-4" /> Initiate transfer
            </CardTitle>
            <CardDescription>FEFO drain from source. Ledger recorded.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Field label="From facility">
              <Select value={tFrom} onChange={(e) => setTFrom(e.target.value)}>
                <option value="">Select…</option>
                {(facilities.data ?? []).map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="To facility">
              <Select value={tTo} onChange={(e) => setTTo(e.target.value)}>
                <option value="">Select…</option>
                {(facilities.data ?? []).map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Item">
              <Select value={tItem} onChange={(e) => setTItem(e.target.value)}>
                <option value="">Select…</option>
                {(items.data ?? []).map((it) => (
                  <option key={it.id} value={it.id}>
                    {it.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Quantity">
              <Input
                type="number"
                min={1}
                value={tQty}
                onChange={(e) => setTQty(Number(e.target.value))}
              />
            </Field>
            <Field label="Reason">
              <Input value={tReason} onChange={(e) => setTReason(e.target.value)} />
            </Field>
            <Button
              className="w-full"
              disabled={!tFrom || !tTo || !tItem || tQty < 1 || transfer.isPending}
              onClick={doTransfer}
            >
              {transfer.isPending ? "Transferring…" : "Transfer"}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Dispense — pharmacist-only on the backend, but the UI is visible to
          all workers so they can see what their pharmacy colleagues see. */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PillBottle className="h-4 w-4" aria-hidden /> Dispense from this facility
          </CardTitle>
          <CardDescription>
            FEFO drain across batches at <strong>{session.name ? session.name + " — " : ""}
            this facility</strong>. Recorded in the hash-chained supply ledger and the audit log.
            Pharmacist role required on the backend.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-4">
            <Field label="Item">
              <Select value={dItem} onChange={(e) => setDItem(e.target.value)}>
                <option value="">Select…</option>
                {(items.data ?? []).map((it) => (
                  <option key={it.id} value={it.id}>
                    {it.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Quantity">
              <Input
                type="number"
                min={1}
                value={dQty}
                onChange={(e) => setDQty(Number(e.target.value))}
              />
            </Field>
            <Field label="Purpose">
              <Select value={dPurpose} onChange={(e) => setDPurpose(e.target.value)}>
                <option value="medication-dispense">Medication dispense</option>
                <option value="vaccination">Vaccination</option>
                <option value="wastage">Wastage / expiry write-off</option>
                <option value="stock-correction">Stock correction</option>
              </Select>
            </Field>
            <div className="flex items-end">
              <Button
                className="w-full"
                disabled={!dItem || dQty < 1 || dispense.isPending || !session.facility_id}
                onClick={doDispense}
              >
                {dispense.isPending ? "Dispensing…" : "Dispense"}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs">{label}</Label>
      {children}
    </div>
  );
}
