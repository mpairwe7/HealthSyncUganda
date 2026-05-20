import * as React from "react";
import {
  AlertTriangle,
  ArrowUp,
  CheckCircle2,
  CircleAlert,
  CircleDashed,
  CircleMinus,
  CircleX,
  Clock,
  Unplug,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils/cn";

/*
 * The single reserved pattern for status communication — per §4.5 of
 * docs/DESIGN_SYSTEM.md. Status is ALWAYS colour + icon + text label, never
 * colour alone. Authors choose a `kind`; the component fixes the rest.
 */
export type StatusKind =
  | "synced"
  | "pending"
  | "failed"
  | "stock-ok"
  | "stock-low"
  | "stock-out"
  | "breaker-open"
  | "breaker-half"
  | "neutral";

type Spec = {
  Icon: LucideIcon;
  className: string;
  defaultLabel: string;
};

const SPECS: Record<StatusKind, Spec> = {
  synced: {
    Icon: CheckCircle2,
    className: "bg-success-soft text-success border-success/30",
    defaultLabel: "Synced",
  },
  pending: {
    Icon: Clock,
    className: "bg-warning-soft text-warning border-warning/30",
    defaultLabel: "Pending sync",
  },
  failed: {
    Icon: AlertTriangle,
    className: "bg-danger-soft text-danger border-danger/30",
    defaultLabel: "Sync failed",
  },
  "stock-ok": {
    Icon: ArrowUp,
    className: "bg-success-soft text-success border-success/30",
    defaultLabel: "Stock OK",
  },
  "stock-low": {
    Icon: CircleMinus,
    className: "bg-warning-soft text-warning border-warning/30",
    defaultLabel: "Low",
  },
  "stock-out": {
    Icon: CircleX,
    className: "bg-danger-soft text-danger border-danger/30",
    defaultLabel: "Stock-out",
  },
  "breaker-open": {
    Icon: Unplug,
    className: "bg-danger-soft text-danger border-danger/30",
    defaultLabel: "Breaker open",
  },
  "breaker-half": {
    Icon: CircleDashed,
    className: "bg-warning-soft text-warning border-warning/30",
    defaultLabel: "Probing",
  },
  neutral: {
    Icon: CircleAlert,
    className: "bg-muted text-muted-foreground border-border",
    defaultLabel: "No data",
  },
};

export interface StatusBadgeProps
  extends React.HTMLAttributes<HTMLSpanElement> {
  kind: StatusKind;
  label?: string;
  size?: "sm" | "md";
}

export const StatusBadge = React.forwardRef<HTMLSpanElement, StatusBadgeProps>(
  ({ kind, label, size = "md", className, ...rest }, ref) => {
    const spec = SPECS[kind];
    const text = label ?? spec.defaultLabel;
    return (
      <span
        ref={ref}
        role="status"
        aria-label={text}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border font-medium",
          size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
          spec.className,
          className,
        )}
        {...rest}
      >
        <spec.Icon className={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} aria-hidden />
        <span>{text}</span>
      </span>
    );
  },
);
StatusBadge.displayName = "StatusBadge";
