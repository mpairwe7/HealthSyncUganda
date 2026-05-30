"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { format } from "date-fns";
import { AlertTriangle, Baby, ExternalLink } from "lucide-react";

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
import { useMyFamily } from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";

function ageYears(birth: string): number {
  const ms = Date.now() - new Date(birth).getTime();
  return Math.floor(ms / (365.25 * 24 * 3600 * 1000));
}

export default function CitizenFamilyPage() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();

  useEffect(() => {
    if (hydrated && !session) router.replace("/citizen/login");
  }, [hydrated, session, router]);

  const family = useMyFamily(!!session);

  if (!hydrated || !session) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">My family</h1>
        <p className="text-muted-foreground">
          Children you are registered as a caregiver for. Each card shows the next vaccine due —
          tap to open that child&apos;s record.
        </p>
      </div>

      <OfflineBanner />

      {family.isLoading ? (
        <Skeleton className="h-32" />
      ) : (family.data ?? []).length === 0 ? (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Baby className="h-5 w-5 text-primary" aria-hidden />
              <CardTitle>No children linked yet</CardTitle>
            </div>
            <CardDescription>
              When you visit a facility with your child, the worker can register you as their
              caregiver. After that, your child appears here and you can see their immunisation
              schedule alongside your own.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {(family.data ?? []).map((m) => {
            const age = ageYears(m.birth_date);
            return (
              <Card key={m.link_id} className={m.overdue_antigen_count > 0 ? "border-amber-300" : undefined}>
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <CardTitle className="text-base">
                        {m.given_name} {m.family_name}
                      </CardTitle>
                      <CardDescription>
                        {age === 0 ? "<1 year" : `${age}y`} · {m.gender} ·{" "}
                        <span className="font-mono text-xs">{m.nin}</span>
                      </CardDescription>
                    </div>
                    <Badge variant="default" className="capitalize">
                      {m.relationship}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  {m.overdue_antigen_count > 0 ? (
                    <div className="flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                      <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
                      <span>
                        <strong>{m.overdue_antigen_count}</strong> antigen
                        {m.overdue_antigen_count > 1 ? "s" : ""} overdue — visit a facility this week.
                      </span>
                    </div>
                  ) : (
                    <div className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
                      All routine vaccines up to date.
                    </div>
                  )}
                  <div className="text-xs text-muted-foreground">
                    Born {format(new Date(m.birth_date), "yyyy-MM-dd")}
                  </div>
                  <Link href={`/citizen/family/${m.patient_id}` as never}>
                    <Button variant="outline" size="sm" className="w-full">
                      Open record <ExternalLink className="ml-1 h-3 w-3" aria-hidden />
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
