"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PackagePlus } from "lucide-react";

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
import { useReceiveStock, useSupplyItems } from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";

export default function ReceiveStockPage() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();

  useEffect(() => {
    if (hydrated && !session) router.replace("/login");
  }, [hydrated, session, router]);

  const items = useSupplyItems();
  const receive = useReceiveStock();

  const [supplyItemId, setSupplyItemId] = useState("");
  const [lotNumber, setLotNumber] = useState("");
  const [quantity, setQuantity] = useState<number | "">("");
  const [expiresOn, setExpiresOn] = useState("");
  const today = new Date().toISOString().slice(0, 10);
  const [receivedOn, setReceivedOn] = useState(today);
  const [costUgx, setCostUgx] = useState<number | "">("");

  if (!hydrated || !session) return null;
  if (!session.facility_id) {
    return (
      <Card className="mx-auto max-w-md mt-8">
        <CardHeader>
          <CardTitle>No facility on session</CardTitle>
          <CardDescription>
            Stock can only be received against a facility. Ask an admin to assign you one.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  async function onReceive(e: React.FormEvent) {
    e.preventDefault();
    if (!supplyItemId || !quantity || !lotNumber || !expiresOn || !session?.facility_id) return;
    try {
      await receive.mutateAsync({
        supply_item_id: supplyItemId,
        facility_id: session.facility_id,
        lot_number: lotNumber,
        quantity: Number(quantity),
        expires_on: expiresOn,
        received_on: receivedOn,
        cost_ugx: typeof costUgx === "number" ? costUgx : null,
      });
      // Reset form for the next batch
      setSupplyItemId("");
      setLotNumber("");
      setQuantity("");
      setExpiresOn("");
      setCostUgx("");
    } catch {
      // Toast surfaced by the mutation hook's onError handler.
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Receive new stock</h1>
        <p className="text-muted-foreground">
          Record a delivery from National Medical Stores (NMS), JMS, or any donor.
        </p>
      </div>

      <OfflineBanner note="Offline — the batch will queue and sync when the network returns." />

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <PackagePlus className="h-5 w-5 text-primary" aria-hidden />
            <CardTitle>Batch details</CardTitle>
          </div>
          <CardDescription>
            Each receipt adds a new batch. Lot number + expiry are mandatory for traceability.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4 sm:grid-cols-2" onSubmit={onReceive}>
            <div className="sm:col-span-2">
              <Label htmlFor="supply-item">Supply item</Label>
              <select
                id="supply-item"
                value={supplyItemId}
                onChange={(e) => setSupplyItemId(e.target.value)}
                required
                className="mt-1 block w-full rounded-md border border-input bg-background px-2 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="">— select —</option>
                {(items.data ?? []).map((it) => (
                  <option key={it.id} value={it.id}>
                    {it.name} ({it.code})
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
                required
                maxLength={80}
                placeholder="e.g. NMS-2026-001"
              />
            </div>
            <div>
              <Label htmlFor="qty">Quantity</Label>
              <Input
                id="qty"
                type="number"
                min={1}
                value={quantity}
                onChange={(e) => setQuantity(e.target.value ? Number(e.target.value) : "")}
                required
              />
            </div>

            <div>
              <Label htmlFor="received">Received on</Label>
              <Input
                id="received"
                type="date"
                max={today}
                value={receivedOn}
                onChange={(e) => setReceivedOn(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="expiry">Expires on</Label>
              <Input
                id="expiry"
                type="date"
                min={today}
                value={expiresOn}
                onChange={(e) => setExpiresOn(e.target.value)}
                required
              />
            </div>

            <div className="sm:col-span-2">
              <Label htmlFor="cost">Unit value (UGX, optional)</Label>
              <Input
                id="cost"
                type="number"
                min={0}
                value={costUgx}
                onChange={(e) => setCostUgx(e.target.value ? Number(e.target.value) : "")}
                placeholder="0"
              />
            </div>

            <div className="sm:col-span-2 flex gap-2">
              <Button type="submit" disabled={receive.isPending}>
                {receive.isPending ? "Recording…" : "Record receipt"}
              </Button>
              <Link href="/worker/supply">
                <Button type="button" variant="outline">
                  Back to supply
                </Button>
              </Link>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
