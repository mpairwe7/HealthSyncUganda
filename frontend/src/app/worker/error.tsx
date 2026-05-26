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

export default function WorkerError({ error, reset }: Props) {
  useEffect(() => {
    // Log to console (and any RUM agent if wired) so production traffic
    // surfaces failures without the page being silently broken.
    console.error("Worker route error:", error);
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
            Patient and supply records were not affected. Try again, or return to the worker
            dashboard.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {error.digest && (
            <p className="font-mono text-xs text-amber-900/70">Trace ID: {error.digest}</p>
          )}
          <div className="flex gap-2">
            <Button variant="default" onClick={reset}>
              Try again
            </Button>
            <Link href="/worker">
              <Button variant="outline">Back to worker dashboard</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
