/**
 * ScopeNote — used by feature pages that are wired into the navigation
 * but whose implementation is scheduled for the pilot phase, not the
 * showcase prototype. Keeps the navigation smooth (no 404s) and is
 * explicit with reviewers about prototype scope.
 */
import Link from "next/link";
import { Construction } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface Props {
  title: string;
  description: string;
  /** Bullet list of what the feature will do once implemented. */
  scopeBullets: string[];
  /** Where to go back to — typically the parent dashboard. */
  backHref: string;
  backLabel?: string;
}

export function ScopeNote({
  title,
  description,
  scopeBullets,
  backHref,
  backLabel = "Back to dashboard",
}: Props) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{title}</h1>
        <p className="text-muted-foreground">{description}</p>
      </div>

      <Card className="border-amber-300 bg-amber-50">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Construction className="h-5 w-5 text-amber-900" aria-hidden />
            <CardTitle className="text-amber-900">In pilot scope</CardTitle>
          </div>
          <CardDescription className="text-amber-900/80">
            This module is part of the pilot deployment plan (Q3 2026 onward)
            and is not interactive in the showcase prototype.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-amber-900">
              Planned capabilities
            </h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900/90">
              {scopeBullets.map((bullet) => (
                <li key={bullet}>{bullet}</li>
              ))}
            </ul>
          </div>
          <Link href={backHref}>
            <Button variant="outline">{backLabel}</Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}
