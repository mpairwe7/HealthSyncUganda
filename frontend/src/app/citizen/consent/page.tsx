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
import { usePatients } from "@/lib/api/hooks";
import { useAuth } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

type Consent = {
  id: string;
  patient_id: string;
  scope: string;
  purpose: string;
  granted_at: string;
  expires_at: string | null;
  revoked_at: string | null;
};

export default function ConsentPage() {
  const session = useAuth((s) => s.session);
  const router = useRouter();
  const pushToast = useUi((s) => s.pushToast);
  const qc = useQueryClient();
  const [patientId, setPatientId] = useState<string | undefined>();

  useEffect(() => {
    if (!session) router.replace("/citizen/login");
  }, [session, router]);

  const me = usePatients({ q: session?.subject, page: 1 });
  useEffect(() => {
    if (me.data?.items[0]?.id) setPatientId(me.data.items[0].id);
  }, [me.data]);

  const consents = useQuery({
    queryKey: ["consents", patientId],
    queryFn: () => apiRequest<Consent[]>(`/api/v1/consents/by-patient/${patientId}`),
    enabled: !!patientId,
  });

  const revoke = useMutation({
    mutationFn: (id: string) =>
      apiRequest<Consent>(`/api/v1/consents/${id}/revoke`, { method: "POST" }),
    onSuccess: () => {
      pushToast({ kind: "success", title: "Consent revoked" });
      qc.invalidateQueries({ queryKey: ["consents", patientId] });
    },
  });

  if (!session) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Consent centre</h1>
        <p className="text-muted-foreground">
          You decide who can access your record. Revoke at any time.
        </p>
      </div>

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
                    <TableCell className="font-mono text-xs">{c.scope}</TableCell>
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
