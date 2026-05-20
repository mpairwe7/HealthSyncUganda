"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useStaffLogin } from "@/lib/api/hooks";
import { useAuth } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

export default function StaffLoginPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const { mutate, isPending, error } = useStaffLogin();
  const setSession = useAuth((s) => s.setSession);
  const pushToast = useUi((s) => s.pushToast);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutate(
      { identifier, password },
      {
        onSuccess: (data) => {
          setSession({
            token: data.access_token,
            role: data.role,
            subject: data.subject,
            name: data.name,
            facility_id: data.facility_id,
            expiresAt: Date.now() + data.expires_in * 1000,
          });
          pushToast({ kind: "success", title: `Welcome, ${data.name ?? "user"}` });
          const target = data.role === "ministry_admin" || data.role === "district_admin"
            ? "/admin"
            : "/worker";
          router.push(target);
        },
      },
    );
  }

  return (
    <div className="mx-auto max-w-md py-8">
      <Card>
        <CardHeader>
          <CardTitle>Healthcare worker sign-in</CardTitle>
          <CardDescription>
            Staff credentials. Citizens use{" "}
            <a className="underline" href="/citizen/login">
              the NIN portal
            </a>{" "}
            instead.
          </CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                autoComplete="username"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            {error && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {(error as Error).message}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={isPending}>
              {isPending ? "Signing in…" : "Sign in"}
            </Button>
            <p className="text-xs text-muted-foreground">
              Demo accounts:{" "}
              <code className="rounded bg-muted px-1">nurse.gulu</code> /{" "}
              <code className="rounded bg-muted px-1">demo1234</code> · admin /{" "}
              <code className="rounded bg-muted px-1">admin1234</code>.
            </p>
          </CardContent>
        </form>
      </Card>
    </div>
  );
}
