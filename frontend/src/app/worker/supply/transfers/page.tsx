"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { ArrowRight, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { useFacilities, useStockTransfers, useSupplyItems } from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";

type Window = 30 | 90 | 365;
const WINDOWS: Window[] = [30, 90, 365];

export default function StockTransfersPage() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();
  const [window, setWindow] = useState<Window>(90);
  const [scope, setScope] = useState<"my-facility" | "all">("my-facility");

  useEffect(() => {
    if (hydrated && !session) router.replace("/login");
  }, [hydrated, session, router]);

  const facilities = useFacilities();
  const items = useSupplyItems();
  const facilityById = useMemo(
    () => new Map((facilities.data ?? []).map((f) => [f.id, f])),
    [facilities.data],
  );
  const itemById = useMemo(
    () => new Map((items.data ?? []).map((it) => [it.id, it])),
    [items.data],
  );

  const transfers = useStockTransfers(
    {
      since_days: window,
      ...(scope === "my-facility" && session?.facility_id
        ? { facility_id: session.facility_id }
        : {}),
    },
    !!session,
  );

  if (!hydrated || !session) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Stock transfers</h1>
        <p className="text-muted-foreground">
          History of inter-facility batch movements. Source facility and destination both
          contribute to the count.
        </p>
      </div>

      <OfflineBanner />

      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-muted-foreground">Window:</span>
        {WINDOWS.map((w) => (
          <Button
            key={w}
            size="sm"
            variant={window === w ? "default" : "outline"}
            onClick={() => setWindow(w)}
          >
            {w === 365 ? "1 year" : `${w} days`}
          </Button>
        ))}
        <span className="ml-4 text-sm text-muted-foreground">Scope:</span>
        <Button
          size="sm"
          variant={scope === "my-facility" ? "default" : "outline"}
          onClick={() => setScope("my-facility")}
          disabled={!session.facility_id}
        >
          My facility
        </Button>
        <Button
          size="sm"
          variant={scope === "all" ? "default" : "outline"}
          onClick={() => setScope("all")}
        >
          All facilities
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => transfers.refetch()}
          disabled={transfers.isFetching}
          aria-label="Refresh"
        >
          <RefreshCw className={"h-4 w-4 " + (transfers.isFetching ? "animate-spin" : "")} />
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{(transfers.data ?? []).length} transfers in the selected window</CardTitle>
          <CardDescription>
            Initiate a new transfer from the{" "}
            <Link href="/worker/supply" className="underline">
              supply page
            </Link>
            . Completed transfers cannot be undone — see the audit log for the trail.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {transfers.isLoading ? (
            <Skeleton className="h-32" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Initiated</TableHead>
                  <TableHead>Item</TableHead>
                  <TableHead>From</TableHead>
                  <TableHead></TableHead>
                  <TableHead>To</TableHead>
                  <TableHead className="text-right">Qty</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(transfers.data ?? []).map((t) => {
                  const item = itemById.get(t.supply_item_id);
                  const from = facilityById.get(t.from_facility_id);
                  const to = facilityById.get(t.to_facility_id);
                  return (
                    <TableRow key={t.id}>
                      <TableCell className="text-xs">
                        {format(new Date(t.initiated_at), "yyyy-MM-dd HH:mm")}
                      </TableCell>
                      <TableCell>{item?.name ?? t.supply_item_id}</TableCell>
                      <TableCell>{from?.name ?? t.from_facility_id.slice(0, 8) + "…"}</TableCell>
                      <TableCell>
                        <ArrowRight className="h-4 w-4 text-muted-foreground" aria-hidden />
                      </TableCell>
                      <TableCell>{to?.name ?? t.to_facility_id.slice(0, 8) + "…"}</TableCell>
                      <TableCell className="text-right font-mono">{t.quantity}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            t.status === "completed"
                              ? "success"
                              : t.status === "abandoned"
                              ? "destructive"
                              : "default"
                          }
                        >
                          {t.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{t.reason}</TableCell>
                    </TableRow>
                  );
                })}
                {(transfers.data ?? []).length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={8}
                      className="py-8 text-center text-sm text-muted-foreground"
                    >
                      No transfers in the selected window.
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
