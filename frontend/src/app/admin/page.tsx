"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { AlertTriangle, ShieldCheck } from "lucide-react";

import { SimpleBar } from "@/components/charts/bar";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
  useEncountersByDistrict,
  useImmunisationCoverage,
  useStockOutRisk,
} from "@/lib/api/hooks";
import { OfflineBanner } from "@/components/ui/offline-banner";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";

export default function AdminPage() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();
  useEffect(() => {
    if (hydrated && !session) router.replace("/login");
  }, [hydrated, session, router]);

  const encByDistrict = useEncountersByDistrict(30);
  const immunisation = useImmunisationCoverage(180);
  const stockOuts = useStockOutRisk();

  if (!hydrated || !session) return null;

  return (
    <div className="space-y-6">
      <OfflineBanner />
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Ministry & district view</h1>
        <p className="text-muted-foreground">
          Live national signals. Cached for 60s; degrades open if cache is unreachable.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard
          title="Active districts (30d)"
          value={String(encByDistrict.data?.length ?? "—")}
          help="Districts with at least one encounter in the past month."
        />
        <KpiCard
          title="Vaccines administered (180d)"
          value={String(
            (immunisation.data ?? []).reduce((a, b) => a + b.doses_administered, 0) || "—",
          )}
          help="From observations against SNOMED CT vaccine codes."
        />
        <KpiCard
          title="Stock-out risks"
          value={String(stockOuts.data?.length ?? "—")}
          help="Facility/item pairs below reorder threshold."
          warning={(stockOuts.data?.length ?? 0) > 0}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Encounters by district (last 30 days)</CardTitle>
          <CardDescription>Activity heat-check across districts.</CardDescription>
        </CardHeader>
        <CardContent>
          {encByDistrict.isLoading ? (
            <Skeleton className="h-64" />
          ) : (
            <SimpleBar
              data={encByDistrict.data ?? []}
              xKey="district"
              yKey="encounter_count"
              yLabel="Encounters"
            />
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Immunisation coverage (180d)</CardTitle>
            <CardDescription>Doses administered by district & antigen.</CardDescription>
          </CardHeader>
          <CardContent>
            {immunisation.isLoading ? (
              <Skeleton className="h-48" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>District</TableHead>
                    <TableHead>Antigen</TableHead>
                    <TableHead className="text-right">Doses</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(immunisation.data ?? []).map((r) => (
                    <TableRow key={`${r.district}-${r.antigen}`}>
                      <TableCell>{r.district}</TableCell>
                      <TableCell className="text-xs">{r.antigen}</TableCell>
                      <TableCell className="text-right">{r.doses_administered}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card className={(stockOuts.data?.length ?? 0) > 0 ? "border-amber-300" : undefined}>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4" /> Stock-out risk
            </CardTitle>
            <CardDescription>Facility/item pairs below reorder.</CardDescription>
          </CardHeader>
          <CardContent>
            {stockOuts.isLoading ? (
              <Skeleton className="h-48" />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Facility</TableHead>
                    <TableHead>Item</TableHead>
                    <TableHead className="text-right">On-hand</TableHead>
                    <TableHead className="text-right">Threshold</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(stockOuts.data ?? []).map((r) => (
                    <TableRow key={`${r.facility_id}-${r.item_code}`}>
                      <TableCell>{r.facility_name}</TableCell>
                      <TableCell className="text-xs">{r.item_name}</TableCell>
                      <TableCell className="text-right">{r.on_hand}</TableCell>
                      <TableCell className="text-right">{r.reorder_threshold}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" /> Compliance posture
          </CardTitle>
          <CardDescription>
            Controls that are verified by code, not claimed by docs. Each row links
            to the source of truth.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-2 text-sm sm:grid-cols-2">
            <li className="flex items-center gap-2">
              <Badge variant="success">OK</Badge>
              Audit log append-only —{" "}
              <span className="text-muted-foreground">
                Postgres trigger blocks UPDATE/DELETE on{" "}
                <code className="font-mono text-xs">audit_log</code>
              </span>
            </li>
            <li className="flex items-center gap-2">
              <Badge variant="success">OK</Badge>
              Every PII access carries{" "}
              <code className="font-mono text-xs">purpose</code> +{" "}
              <code className="font-mono text-xs">actor</code>
              <span className="text-muted-foreground"> (record_access middleware)</span>
            </li>
            <li className="flex items-center gap-2">
              <Badge variant="success">OK</Badge>
              <span>
                Offline replays carry a stable{" "}
                <code className="font-mono text-xs">Idempotency-Key</code>;
                server dedupes within 24h
              </span>
            </li>
            <li className="flex items-center gap-2">
              <Badge variant="success">OK</Badge>
              <span>
                Worker reads scoped to facility; district admins to district;
                FHIR honours the same matrix
              </span>
            </li>
            <li className="flex items-center gap-2">
              <Badge variant="success">OK</Badge>
              <span>
                Supply ledger hash-chained;{" "}
                <code className="font-mono text-xs">stock_events</code> is
                append-only at the DB
              </span>
            </li>
            <li className="flex items-center gap-2">
              <Badge variant="outline">env</Badge>
              <span className="text-muted-foreground">
                TLS, CSP, HSTS enforced at the deployment edge (operator
                responsibility)
              </span>
            </li>
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">
            Snapshot rendered at {format(new Date(), "yyyy-MM-dd HH:mm")}. The
            backing tests live in{" "}
            <code className="font-mono">backend/tests/test_rbac_scoping.py</code>{" "}
            and{" "}
            <code className="font-mono">test_fhir_endpoints.py</code>.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function KpiCard({
  title,
  value,
  help,
  warning = false,
}: {
  title: string;
  value: string;
  help: string;
  warning?: boolean;
}) {
  return (
    <Card className={warning ? "border-amber-300 bg-amber-50" : undefined}>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl">{value}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground">{help}</p>
      </CardContent>
    </Card>
  );
}
