"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ExternalLink, MapPin } from "lucide-react";

import { Badge } from "@/components/ui/badge";
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
import { useFacilities } from "@/lib/api/hooks";
import { useAuth, useAuthHydrated } from "@/lib/store/auth";
import { useUi } from "@/lib/store/ui";

export default function CitizenFacilitiesPage() {
  const session = useAuth((s) => s.session);
  const hydrated = useAuthHydrated();
  const router = useRouter();
  const online = useUi((s) => s.online);
  const [district, setDistrict] = useState<string>("");

  useEffect(() => {
    if (hydrated && !session) router.replace("/citizen/login");
  }, [hydrated, session, router]);

  const facilities = useFacilities();
  const allFacilities = facilities.data ?? [];

  const districts = useMemo(
    () => Array.from(new Set(allFacilities.map((f) => f.district))).sort(),
    [allFacilities],
  );
  const filtered = useMemo(
    () =>
      (district ? allFacilities.filter((f) => f.district === district) : allFacilities)
        .slice()
        .sort((a, b) => a.district.localeCompare(b.district) || a.name.localeCompare(b.name)),
    [allFacilities, district],
  );

  if (!hydrated || !session) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Find a facility</h1>
        <p className="text-muted-foreground">
          MoH-accredited facilities across the network. Pick a district to narrow
          the list.
        </p>
      </div>

      {!online && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          Offline — showing the last synced facility list.
        </div>
      )}

      <div className="flex items-center gap-2">
        <label className="text-sm text-muted-foreground" htmlFor="district">
          District:
        </label>
        <select
          id="district"
          value={district}
          onChange={(e) => setDistrict(e.target.value)}
          className="rounded-md border border-input bg-background px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">All districts ({allFacilities.length})</option>
          {districts.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <MapPin className="h-5 w-5 text-primary" aria-hidden />
            <CardTitle>Facilities ({filtered.length})</CardTitle>
          </div>
          <CardDescription>
            Click "Directions" to open the location in OpenStreetMap.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {facilities.isLoading ? (
            <Skeleton className="h-32" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>District</TableHead>
                  <TableHead>Facility</TableHead>
                  <TableHead>Level</TableHead>
                  <TableHead className="text-right">Directions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((f) => (
                  <TableRow key={f.id}>
                    <TableCell>{f.district}</TableCell>
                    <TableCell>{f.name}</TableCell>
                    <TableCell>
                      <Badge variant="default" className="font-mono text-xs">
                        {f.level}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      {f.latitude != null && f.longitude != null ? (
                        <a
                          href={`https://www.openstreetmap.org/?mlat=${f.latitude}&mlon=${f.longitude}#map=15/${f.latitude}/${f.longitude}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-sm text-primary underline-offset-4 hover:underline"
                        >
                          Open <ExternalLink className="h-3 w-3" aria-hidden />
                        </a>
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell
                      colSpan={4}
                      className="py-8 text-center text-sm text-muted-foreground"
                    >
                      No facilities match the selected filter.
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
