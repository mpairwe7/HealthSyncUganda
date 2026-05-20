"use client";

import Link from "next/link";
import {
  Activity,
  HeartPulse,
  Map,
  ShieldCheck,
  Wifi,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useT } from "@/lib/i18n/provider";

export default function Page() {
  const { t } = useT();
  return (
    <div className="space-y-12 py-6">
      <section className="grid items-center gap-6 lg:grid-cols-2">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wide text-primary">
            {t.landing.eyebrow}
          </p>
          <h1 className="mt-2 text-4xl font-bold tracking-tight sm:text-5xl">
            {t.landing.heading}
          </h1>
          <p className="mt-4 max-w-xl text-lg text-muted-foreground">
            {t.landing.sub}
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            <Link href="/citizen/login">
              <Button size="lg">{t.landing.ctaCitizen}</Button>
            </Link>
            <Link href="/login">
              <Button variant="outline" size="lg">
                {t.landing.ctaWorker}
              </Button>
            </Link>
          </div>
        </div>
        <div className="hidden lg:block">
          <div className="rounded-2xl border bg-card p-8 shadow-sm">
            <div className="grid grid-cols-2 gap-4">
              <Feature
                icon={<HeartPulse className="h-5 w-5 text-primary" />}
                title={t.landing.pillars.nin.title}
                description={t.landing.pillars.nin.desc}
              />
              <Feature
                icon={<Wifi className="h-5 w-5 text-primary" />}
                title={t.landing.pillars.offline.title}
                description={t.landing.pillars.offline.desc}
              />
              <Feature
                icon={<Activity className="h-5 w-5 text-primary" />}
                title={t.landing.pillars.fhir.title}
                description={t.landing.pillars.fhir.desc}
              />
              <Feature
                icon={<Map className="h-5 w-5 text-primary" />}
                title={t.landing.pillars.supply.title}
                description={t.landing.pillars.supply.desc}
              />
            </div>
            <div className="mt-6 flex items-start gap-3 rounded-lg bg-accent p-4">
              <ShieldCheck className="mt-0.5 h-5 w-5 text-primary" />
              <div className="text-sm">
                <p className="font-medium text-accent-foreground">
                  Built for the National Innovator Registry
                </p>
                <p className="text-muted-foreground">
                  Production-quality observability, audit, and graceful degradation
                  — out of the box.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <UserCard
          title={t.landing.cards.citizen.title}
          description={t.landing.cards.citizen.desc}
          href="/citizen"
          open={t.landing.open}
        />
        <UserCard
          title={t.landing.cards.worker.title}
          description={t.landing.cards.worker.desc}
          href="/worker"
          open={t.landing.open}
        />
        <UserCard
          title={t.landing.cards.admin.title}
          description={t.landing.cards.admin.desc}
          href="/admin"
          open={t.landing.open}
        />
      </section>
    </div>
  );
}

function Feature({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="mt-0.5">{icon}</div>
      <div>
        <p className="font-semibold">{title}</p>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}

function UserCard({
  title,
  description,
  href,
  open,
}: {
  title: string;
  description: string;
  href: "/citizen" | "/worker" | "/admin";
  open: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <Link href={href}>
          <Button variant="outline" className="w-full">
            {open}
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}
