"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";

import { apiRequest } from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useGrantOwnConsent, useMe } from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

import type { ConsentOut, ConsentScope } from "@/types/api";

const SCOPE_LABELS: Record<ConsentScope, string> = {
  share_records_across_facilities: "Share records across facilities",
  share_with_district_health_office: "Share with district health office",
  share_with_research: "Share with research (de-identified)",
  share_with_emergency_services: "Share with emergency services",
};

export default function ConsentPage() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();
  const pushToast = useUi((s) => s.pushToast);
  const online = useUi((s) => s.online);
  const qc = useQueryClient();
  const grantOwn = useGrantOwnConsent();
  const [newScope, setNewScope] = useState<ConsentScope>("share_with_emergency_services");
  const [newPurpose, setNewPurpose] = useState("Emergency care");

  useEffect(() => {
    if (hydrated && !session) router.replace("/citizen/login");
  }, [hydrated, session, router]);

  const me = useMe(!!session);
  const patientId = me.data?.id;

  const consents = useQuery({
    queryKey: ["consents", patientId],
    queryFn: () => apiRequest<ConsentOut[]>(`/api/v1/consents/by-patient/${patientId}`),
    enabled: !!patientId,
  });

  const revoke = useMutation({
    mutationFn: (id: string) =>
      apiRequest<ConsentOut>(`/api/v1/consents/${id}/revoke`, { method: "POST" }),
    onSuccess: () => {
      pushToast({ kind: "success", title: "Consent revoked" });
      qc.invalidateQueries({ queryKey: ["consents", patientId] });
    },
  });

  function onGrant(e: React.FormEvent) {
    e.preventDefault();
    grantOwn.mutate(
      { scope: newScope, purpose: newPurpose },
      {
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: ["consents", patientId] });
        },
      },
    );
  }

  if (!hydrated || !session) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Consent centre</h1>
        <p className="text-muted-foreground">
          You decide who can access your record. Revoke at any time.
        </p>
      </div>

      {!online && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Offline — granting and revoking will sync when you reconnect.
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Grant a new consent</CardTitle>
          <CardDescription>
            You can grant a specific scope (e.g. emergency-care access). The
            grant is recorded against your record and visible in Access history.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 sm:grid-cols-[1fr,2fr,auto]" onSubmit={onGrant}>
            <div>
              <label className="text-xs uppercase tracking-wide text-muted-foreground">
                Scope
              </label>
              <select
                value={newScope}
                onChange={(e) => setNewScope(e.target.value as ConsentScope)}
                className="mt-1 block w-full rounded-md border border-input bg-background px-2 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {(Object.keys(SCOPE_LABELS) as ConsentScope[]).map((s) => (
                  <option key={s} value={s}>
                    {SCOPE_LABELS[s]}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs uppercase tracking-wide text-muted-foreground">
                Purpose
              </label>
              <input
                type="text"
                value={newPurpose}
                onChange={(e) => setNewPurpose(e.target.value)}
                minLength={4}
                maxLength={300}
                required
                className="mt-1 block w-full rounded-md border border-input bg-background px-2 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="e.g. Emergency care"
              />
            </div>
            <div className="flex items-end">
              <Button type="submit" disabled={grantOwn.isPending}>
                {grantOwn.isPending ? "Granting…" : "Grant consent"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Active consents</CardTitle>
          <CardDescription>
            Explicit permissions for specific purposes. Required by Uganda&apos;s Data
            Protection &amp; Privacy Act.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {consents.isLoading ? (
            <Skeleton className="h-32" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scope</TableHead>
                  <TableHead>Purpose</TableHead>
                  <TableHead>Granted</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(consents.data ?? []).map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="text-sm">
                      {SCOPE_LABELS[c.scope] ?? c.scope}
                    </TableCell>
                    <TableCell>{c.purpose}</TableCell>
                    <TableCell>{format(new Date(c.granted_at), "yyyy-MM-dd")}</TableCell>
                    <TableCell>
                      <Badge variant={c.revoked_at ? "destructive" : "success"}>
                        {c.revoked_at ? "revoked" : "active"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {!c.revoked_at && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => revoke.mutate(c.id)}
                        >
                          Revoke
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {(consents.data ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                      No consents yet. Workers will request consent when you visit a facility.
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
