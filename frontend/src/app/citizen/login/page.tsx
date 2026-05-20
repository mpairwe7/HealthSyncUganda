"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CircleHelp, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCitizenLogin } from "@/lib/api/hooks";
import { useT } from "@/lib/i18n/provider";
import { useAuth } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

export default function CitizenLoginPage() {
  const router = useRouter();
  const [nin, setNin] = useState("");
  const [otp, setOtp] = useState("");
  const setSession = useAuth((s) => s.setSession);
  const pushToast = useUi((s) => s.pushToast);
  const { mutate, isPending, error } = useCitizenLogin();
  const { t } = useT();

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutate(
      { nin: nin.trim().toUpperCase(), otp: otp.trim() },
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
          pushToast({
            kind: "success",
            title: t.citizenLogin.welcome(data.name ?? t.citizenHome.welcomeFallback),
          });
          router.push("/citizen");
        },
      },
    );
  }

  return (
    <div className="mx-auto max-w-md py-8">
      <Card>
        <CardHeader>
          <CardTitle>{t.citizenLogin.title}</CardTitle>
          <CardDescription>{t.citizenLogin.description}</CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit}>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="nin">{t.citizenLogin.ninLabel}</Label>
              <Input
                id="nin"
                inputMode="text"
                autoComplete="off"
                placeholder="CM85051712345X"
                maxLength={14}
                required
                value={nin}
                onChange={(e) => setNin(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{t.citizenLogin.ninHelp}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="otp">{t.citizenLogin.otpLabel}</Label>
              <Input
                id="otp"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="000000"
                maxLength={8}
                required
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                {t.citizenLogin.otpHelpDemo}{" "}
                <code className="rounded bg-muted px-1">000000</code>.{" "}
                {t.citizenLogin.otpHelpReal}
              </p>
            </div>
            {error && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {(error as Error).message}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={isPending}>
              {isPending ? t.citizenLogin.submitting : t.citizenLogin.submit}
            </Button>
            <p className="flex items-start gap-2 rounded-md bg-accent p-3 text-xs text-accent-foreground">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{t.citizenLogin.audit}</span>
            </p>
            <p className="flex items-start gap-2 text-xs text-muted-foreground">
              <CircleHelp className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                Don&apos;t have a NIN yet? Visit your nearest NIRA office or{" "}
                <a
                  href="https://www.nira.go.ug"
                  className="underline"
                  rel="noreferrer noopener"
                  target="_blank"
                >
                  nira.go.ug
                </a>
                .{" "}
                <Link href="/citizen/audit" className="underline">
                  Access history
                </Link>
                .
              </span>
            </p>
          </CardContent>
        </form>
      </Card>
    </div>
  );
}
