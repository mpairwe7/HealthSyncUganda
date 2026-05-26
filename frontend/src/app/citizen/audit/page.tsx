"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { Eye } from "lucide-react";

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
import { useFacilities, useMyAudit } from "@/lib/api/hooks";
import { useAuth } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

type Window = 7 | 30 | 90;
const WINDOWS: Window[] = [7, 30, 90];

const friendlyAction: Record<string, string> = {
  read: "Read record",
  "read-history": "Viewed history",
  "read-self": "You opened your record",
  "read-history-self": "You opened your history",
  "read-immunisations-self": "You viewed your immunisations",
  "update-profile-self": "You updated your profile",
  "grant-self": "You granted a consent",
  revoke: "Consent revoked",
  grant: "Consent granted",
};

export default function CitizenAuditPage() {
  const session = useAuth((s) => s.session);
  const router = useRouter();
  const online = useUi((s) => s.online);
  const [window, setWindow] = useState<Window>(30);

  useEffect(() => {
    if (!session) router.replace("/citizen/login");
  }, [session, router]);

  const audit = useMyAudit(window, !!session);
  const facilities = useFacilities();
  const facilityById = new Map((facilities.data ?? []).map((f) => [f.id, f]));

  if (!session) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Access history</h1>
        <p className="text-muted-foreground">
          Every read of your record is logged. This is your right under the
          Uganda Data Protection &amp; Privacy Act §14.
        </p>
      </div>

      {!online && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Offline — showing the last synced view of your access log.
        </div>
      )}

      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Show last:</span>
        {WINDOWS.map((w) => (
          <Button
            key={w}
            variant={window === w ? "default" : "outline"}
            size="sm"
            onClick={() => setWindow(w)}
          >
            {w} days
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Eye className="h-5 w-5 text-primary" aria-hidden />
            <CardTitle>Who accessed my record</CardTitle>
          </div>
          <CardDescription>
            Reverse-chronological. Each row is a healthcare worker, your own
            session, or an automated process touching your record.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {audit.isLoading ? (
            <Skeleton className="h-32" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>What</TableHead>
                  <TableHead>Purpose</TableHead>
                  <TableHead>Facility</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(audit.data ?? []).map((row) => {
                  const fac = row.actor_facility_id
                    ? facilityById.get(row.actor_facility_id)
                    : undefined;
                  return (
                    <TableRow key={row.id}>
                      <TableCell className="text-xs">
                        {format(new Date(row.occurred_at), "yyyy-MM-dd HH:mm")}
                      </TableCell>
                      <TableCell>
                        <Badge variant="default" className="capitalize">
                          {row.actor_role.replace("_", " ")}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {friendlyAction[row.action] ?? row.action}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {row.purpose ?? "—"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {fac ? fac.name : "—"}
                      </TableCell>
                    </TableRow>
                  );
                })}
                {(audit.data ?? []).length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={5}
                      className="py-8 text-center text-sm text-muted-foreground"
                    >
                      No accesses logged in the last {window} days.
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
