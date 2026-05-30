"use client";

import Link from "next/link";
import { useEffect } from "react";
import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

interface Props {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function CitizenError({ error, reset }: Props) {
  useEffect(() => {
    // Log to console so it shows up in browser devtools + any RUM agent.
    // Production deployments wire this to OpenTelemetry on the client side.
    console.error("Citizen route error:", error);
  }, [error]);

  return (
    <div className="mx-auto max-w-xl py-8">
      <Card className="border-amber-300 bg-amber-50">
        <CardHeader>
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-900" aria-hidden />
            <CardTitle className="text-amber-900">
              Something went wrong on this page
            </CardTitle>
          </div>
          <CardDescription className="text-amber-900/80">
            Your record was not affected. Try again, or return to the citizen
            home and re-open the page.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {error.digest && (
            <p className="font-mono text-xs text-amber-900/70">
              Trace ID: {error.digest}
            </p>
          )}
          <div className="flex gap-2">
            <Button variant="default" onClick={reset}>
              Try again
            </Button>
            <Link href="/citizen">
              <Button variant="outline">Back to citizen home</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
