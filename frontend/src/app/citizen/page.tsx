"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  CalendarClock,
  ClipboardList,
  FileLock2,
  HeartPulse,
  MapPin,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useT } from "@/lib/i18n/provider";
import { useAuth } from "@/lib/store/auth";

export default function CitizenHomePage() {
  const session = useAuth((s) => s.session);
  const router = useRouter();
  const { t } = useT();

  useEffect(() => {
    if (!session) router.replace("/citizen/login");
  }, [session, router]);

  if (!session) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          {t.citizenHome.welcome(session.name ?? t.citizenHome.welcomeFallback)}
        </h1>
        <p className="text-muted-foreground">{t.citizenHome.sub}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Tile
          icon={<ClipboardList className="h-5 w-5 text-primary" />}
          title={t.citizenHome.tiles.records.title}
          description={t.citizenHome.tiles.records.desc}
          href="/citizen/records"
          open={t.citizenHome.open}
        />
        <Tile
          icon={<FileLock2 className="h-5 w-5 text-primary" />}
          title={t.citizenHome.tiles.consent.title}
          description={t.citizenHome.tiles.consent.desc}
          href="/citizen/consent"
          open={t.citizenHome.open}
        />
        <Tile
          icon={<HeartPulse className="h-5 w-5 text-primary" />}
          title={t.citizenHome.tiles.immunisations.title}
          description={t.citizenHome.tiles.immunisations.desc}
          href="/citizen/immunisations"
          open={t.citizenHome.open}
        />
        <Tile
          icon={<CalendarClock className="h-5 w-5 text-primary" />}
          title={t.citizenHome.tiles.appointments.title}
          description={t.citizenHome.tiles.appointments.desc}
          href="/citizen/appointments"
          open={t.citizenHome.open}
        />
        <Tile
          icon={<MapPin className="h-5 w-5 text-primary" />}
          title={t.citizenHome.tiles.facilities.title}
          description={t.citizenHome.tiles.facilities.desc}
          href="/citizen/facilities"
          open={t.citizenHome.open}
        />
      </div>
    </div>
  );
}

function Tile({
  icon,
  title,
  description,
  href,
  open,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  href: string;
  open: string;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          {icon}
          <CardTitle className="text-base">{title}</CardTitle>
        </div>
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
