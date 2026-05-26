"use client";

import { use, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { ArrowLeft, AlertTriangle, CheckCircle2, Clock, Syringe } from "lucide-react";

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
import { useImmunisationStatus, usePatient } from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";

import type { AntigenStatusOut } from "@/types/api";

function statusBadge(s: AntigenStatusOut["status"]) {
  switch (s) {
    case "complete":  return { variant: "success" as const, icon: CheckCircle2, label: "complete" };
    case "due":       return { variant: "default" as const, icon: Syringe, label: "due now" };
    case "due-soon":  return { variant: "default" as const, icon: Clock, label: "due soon" };
    case "overdue":   return { variant: "warning" as const, icon: AlertTriangle, label: "overdue" };
    case "not-yet":   return { variant: "default" as const, icon: Clock, label: "not yet" };
  }
}

export default function CitizenChildPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();

  useEffect(() => {
    if (hydrated && !session) router.replace("/citizen/login");
  }, [hydrated, session, router]);

  const patient = usePatient(id);
  const status = useImmunisationStatus(id);

  if (!hydrated || !session) return null;

  if (patient.isLoading) return <Skeleton className="h-64" />;
  if (!patient.data) {
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Child record not found</CardTitle>
          <CardDescription>
            You can only view children you&apos;re registered as a caregiver for. If this is your
            child, ask a healthcare worker to link the record.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/citizen/family">
            <Button variant="outline">
              <ArrowLeft className="mr-1 h-4 w-4" aria-hidden /> Back to family
            </Button>
          </Link>
        </CardContent>
      </Card>
    );
  }
  const p = patient.data;

  return (
    <div className="space-y-6">
      <OfflineBanner />
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {p.given_name} {p.family_name}
          </h1>
          <p className="text-muted-foreground">
            <span className="font-mono">{p.nin}</span> · {p.gender} · born{" "}
            {format(new Date(p.birth_date), "yyyy-MM-dd")}
          </p>
        </div>
        <Link href="/citizen/family">
          <Button variant="outline" size="sm">
            <ArrowLeft className="mr-1 h-4 w-4" aria-hidden /> Family
          </Button>
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Immunisation schedule</CardTitle>
          <CardDescription>
            Computed against the UNEPI routine schedule. Overdue rows mean the child should see a
            healthcare worker this week.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {status.isLoading ? (
            <Skeleton className="h-32" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Antigen</TableHead>
                  <TableHead>Progress</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Next due</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(status.data ?? []).map((s) => {
                  const b = statusBadge(s.status);
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
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
