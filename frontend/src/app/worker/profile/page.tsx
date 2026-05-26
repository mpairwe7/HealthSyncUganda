"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Activity, Building2, IdCard, LogOut, ShieldCheck } from "lucide-react";

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
import { useMyStaff } from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";

export default function WorkerProfilePage() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const setSession = useAuth((s) => s.setSession);
  const router = useRouter();

  useEffect(() => {
    if (hydrated && !session) router.replace("/login");
  }, [hydrated, session, router]);

  const me = useMyStaff(!!session && session.role !== "citizen");

  if (!hydrated || !session) return null;

  const expiresAt = new Date(session.expiresAt);
  const minutesLeft = Math.max(0, Math.round((session.expiresAt - Date.now()) / 60_000));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">My profile</h1>
        <p className="text-muted-foreground">
          Staff identity and facility context for the current session.
        </p>
      </div>

      <OfflineBanner />

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <IdCard className="h-5 w-5 text-primary" aria-hidden />
            <CardTitle>Identity</CardTitle>
          </div>
          <CardDescription>From the staff registry — change requests go through an admin.</CardDescription>
        </CardHeader>
        <CardContent>
          {me.isLoading ? (
            <Skeleton className="h-24" />
          ) : me.data ? (
            <dl className="grid gap-3 sm:grid-cols-2 text-sm">
              <Field label="Username" value={me.data.username} mono />
              <Field label="Full name" value={me.data.full_name} />
              <Field
                label="Role"
                render={
                  <Badge variant="default" className="capitalize">
                    {me.data.role.replace("_", " ")}
                  </Badge>
                }
              />
              <Field
                label="Account state"
                render={
                  <Badge variant={me.data.active ? "success" : "destructive"}>
                    {me.data.active ? "active" : "disabled"}
                  </Badge>
                }
              />
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">Could not load staff profile.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Building2 className="h-5 w-5 text-primary" aria-hidden />
            <CardTitle>Facility</CardTitle>
          </div>
          <CardDescription>Your default facility scope for clinical writes and dispense.</CardDescription>
        </CardHeader>
        <CardContent>
          {me.isLoading ? (
            <Skeleton className="h-24" />
          ) : me.data?.facility_id ? (
            <dl className="grid gap-3 sm:grid-cols-3 text-sm">
              <Field label="Name" value={me.data.facility_name ?? "—"} />
              <Field label="Level" value={me.data.facility_level ?? "—"} />
              <Field label="District" value={me.data.facility_district ?? "—"} />
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">
              No facility assigned. Ministry / district admins typically operate without one.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" aria-hidden />
            <CardTitle>Session</CardTitle>
          </div>
          <CardDescription>
            Your current sign-in. Tokens expire on a timer — re-login to refresh.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <dl className="grid gap-3 sm:grid-cols-2 text-sm">
            <Field label="Token expires at" value={expiresAt.toLocaleString()} />
            <Field
              label="Time remaining"
              render={
                <Badge variant={minutesLeft < 30 ? "warning" : "default"}>
                  {minutesLeft} min
                </Badge>
              }
            />
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" aria-hidden />
            <CardTitle>End session</CardTitle>
          </div>
          <CardDescription>
            Clears the token from this device. Other active sessions are not affected — that
            requires the production-tier &quot;sign out everywhere&quot; capability.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="destructive"
            onClick={() => {
              setSession(null);
              router.push("/login");
            }}
          >
            <LogOut className="mr-1.5 h-4 w-4" aria-hidden />
            Sign out
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  label,
  value,
  render,
  mono = false,
}: {
  label: string;
  value?: string;
  render?: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className={mono ? "font-mono" : ""}>{render ?? value ?? "—"}</dd>
    </div>
  );
}
