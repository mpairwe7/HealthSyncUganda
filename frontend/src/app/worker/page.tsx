"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  ClipboardPlus,
  Package,
  Search,
  Stethoscope,
  Syringe,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useStockSnapshot } from "@/lib/api/hooks";
import { useAuth } from "@/lib/store/auth";

export default function WorkerHome() {
  const session = useAuth((s) => s.session);
  const router = useRouter();
  useEffect(() => {
    if (!session) router.replace("/login");
  }, [session, router]);

  const lowStock = useStockSnapshot({ only_below_threshold: true });

  if (!session) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Worker dashboard</h1>
        <p className="text-muted-foreground">
          {session.name ?? session.subject} · {session.role.replace("_", " ")}
        </p>
      </div>

      {lowStock.data && lowStock.data.length > 0 && (
        <Card className="border-amber-300 bg-amber-50">
          <CardHeader>
            <CardTitle className="text-amber-900">
              {lowStock.data.length} items below reorder threshold
            </CardTitle>
            <CardDescription className="text-amber-800">
              Click any item to inspect and initiate a transfer.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/worker/supply">
              <Button variant="outline">Open supply</Button>
            </Link>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Tile
          icon={<Search className="h-5 w-5 text-primary" />}
          title="Find patient"
          description="Search by NIN, name, or phone."
          href="/worker/patients"
        />
        <Tile
          icon={<ClipboardPlus className="h-5 w-5 text-primary" />}
          title="Enrol patient"
          description="Register a new citizen. Works offline."
          href="/worker/patients/new"
        />
        <Tile
          icon={<Stethoscope className="h-5 w-5 text-primary" />}
          title="Record encounter"
          description="Vitals, diagnoses, prescriptions."
          href="/worker/patients"
        />
        <Tile
          icon={<Syringe className="h-5 w-5 text-primary" />}
          title="Immunisations"
          description="Children and adolescents due."
          href="/worker/immunisations"
        />
        <Tile
          icon={<Package className="h-5 w-5 text-primary" />}
          title="Supply"
          description="Stock, batches, transfers."
          href="/worker/supply"
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
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
  href: string;
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
            Open
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}
