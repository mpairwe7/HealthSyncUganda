"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { AlertTriangle, ArrowRightLeft } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
  useFacilities,
  useStockSnapshot,
  useStockTransfer,
  useSupplyItems,
} from "@/lib/api/hooks";
import { useAuth } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

export default function SupplyPage() {
  const session = useAuth((s) => s.session);
  const router = useRouter();
  useEffect(() => {
    if (!session) router.replace("/login");
  }, [session, router]);

  const [district, setDistrict] = useState<string | "">("");
  const snapshot = useStockSnapshot({ district: district || undefined });
  const items = useSupplyItems();
  const facilities = useFacilities();
  const transfer = useStockTransfer();
  const pushToast = useUi((s) => s.pushToast);

  const [tFrom, setTFrom] = useState("");
  const [tTo, setTTo] = useState("");
  const [tItem, setTItem] = useState("");
  const [tQty, setTQty] = useState(50);
  const [tReason, setTReason] = useState("Replenishment");

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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Supply</h1>
        <p className="text-muted-foreground">Live facility-level stock with low-stock alerts.</p>
      </div>

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
