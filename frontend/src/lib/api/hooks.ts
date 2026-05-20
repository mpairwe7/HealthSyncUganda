/**
 * Domain-specific hooks built on top of TanStack Query + the offline queue.
 *
 * Each mutation hook follows the same pattern:
 *   1. Try the request live.
 *   2. If we're offline, enqueue and return optimistic data.
 *   3. Invalidate relevant queries on success.
 */

"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { apiRequest, NetworkOfflineError } from "@/lib/api/client";
import { enqueue } from "@/lib/offline/queue";
import { useUi } from "@/lib/store/ui";

import type {
  EncounterCreate,
  EncounterOut,
  FacilityOut,
  FacilityStockSnapshot,
  ImmunisationCoverage,
  PatientCreate,
  PatientOut,
  PatientSummary,
  PaginatedPatients,
  StockOutRisk,
  StockTransferCreate,
  StockTransferOut,
  SupplyItemOut,
  TokenResponse,
  DistrictEncounterCount,
} from "@/types/api";

// ── Auth ─────────────────────────────────────────────────────────────────────

export function useStaffLogin() {
  return useMutation({
    mutationFn: (body: { identifier: string; password: string }) =>
      apiRequest<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        body,
        noAuth: true,
        idempotent: false,
      }),
  });
}

export function useCitizenLogin() {
  return useMutation({
    mutationFn: (body: { nin: string; otp: string }) =>
      apiRequest<TokenResponse>("/api/v1/auth/citizen/login", {
        method: "POST",
        body,
        noAuth: true,
        idempotent: false,
      }),
  });
}

// ── Patients ─────────────────────────────────────────────────────────────────

export function usePatients(q: { q?: string; district?: string; page?: number }) {
  return useQuery({
    queryKey: ["patients", q],
    queryFn: () =>
      apiRequest<PaginatedPatients>("/api/v1/patients", {
        query: q,
      }),
  });
}

export function usePatient(id: string | undefined) {
  return useQuery({
    queryKey: ["patient", id],
    queryFn: () => apiRequest<PatientOut>(`/api/v1/patients/${id}`),
    enabled: !!id,
  });
}

export function useCreatePatient() {
  const qc = useQueryClient();
  const pushToast = useUi((s) => s.pushToast);
  return useMutation({
    mutationFn: async (body: PatientCreate) => {
      try {
        return await apiRequest<PatientOut>("/api/v1/patients", {
          method: "POST",
          body,
        });
      } catch (err) {
        if (err instanceof NetworkOfflineError) {
          await enqueue({
            method: "POST",
            path: "/api/v1/patients",
            body,
            idempotencyKey: crypto.randomUUID(),
            label: `New patient ${body.given_name} ${body.family_name}`,
          });
          pushToast({
            kind: "info",
            title: "Saved offline",
            description: "Patient will sync when network returns.",
          });
          // Optimistic shape — UI handles "pending" state via the queue indicator
          return {
            id: "pending-" + crypto.randomUUID().slice(0, 8),
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            deceased: false,
            record_version: 1,
            ...body,
          } as unknown as PatientOut;
        }
        throw err;
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["patients"] }),
  });
}

// ── Encounters ───────────────────────────────────────────────────────────────

export function useEncountersByPatient(patientId: string | undefined) {
  return useQuery({
    queryKey: ["encounters", patientId],
    queryFn: () => apiRequest<EncounterOut[]>(`/api/v1/encounters/by-patient/${patientId}`),
    enabled: !!patientId,
  });
}

export function useCreateEncounter() {
  const qc = useQueryClient();
  const pushToast = useUi((s) => s.pushToast);
  return useMutation({
    mutationFn: async (body: EncounterCreate) => {
      try {
        return await apiRequest<EncounterOut>("/api/v1/encounters", {
          method: "POST",
          body,
        });
      } catch (err) {
        if (err instanceof NetworkOfflineError) {
          await enqueue({
            method: "POST",
            path: "/api/v1/encounters",
            body,
            idempotencyKey: crypto.randomUUID(),
            label: `Encounter for ${body.patient_id}`,
          });
          pushToast({
            kind: "info",
            title: "Encounter saved offline",
            description: "Will sync automatically.",
          });
          return null as unknown as EncounterOut;
        }
        throw err;
      }
    },
    onSuccess: (_, vars) =>
      qc.invalidateQueries({ queryKey: ["encounters", vars.patient_id] }),
  });
}

// ── Facilities ───────────────────────────────────────────────────────────────

export function useFacilities(filters?: { district?: string; level?: string }) {
  return useQuery({
    queryKey: ["facilities", filters],
    queryFn: () => apiRequest<FacilityOut[]>("/api/v1/facilities", { query: filters }),
    staleTime: 30 * 60_000,
  });
}

// ── Supply chain ─────────────────────────────────────────────────────────────

export function useSupplyItems() {
  return useQuery({
    queryKey: ["supply", "items"],
    queryFn: () => apiRequest<SupplyItemOut[]>("/api/v1/supply/items"),
  });
}

export function useStockSnapshot(filters?: { district?: string; only_below_threshold?: boolean }) {
  return useQuery({
    queryKey: ["supply", "snapshot", filters],
    queryFn: () =>
      apiRequest<FacilityStockSnapshot[]>("/api/v1/supply/snapshot", { query: filters }),
  });
}

export function useStockTransfer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: StockTransferCreate) =>
      apiRequest<StockTransferOut>("/api/v1/supply/transfers", { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["supply"] }),
  });
}

// ── Analytics ────────────────────────────────────────────────────────────────

export function useEncountersByDistrict(since_days = 30) {
  return useQuery({
    queryKey: ["analytics", "encounters", since_days],
    queryFn: () =>
      apiRequest<DistrictEncounterCount[]>("/api/v1/analytics/encounters-by-district", {
        query: { since_days },
      }),
  });
}

export function useImmunisationCoverage(since_days = 180) {
  return useQuery({
    queryKey: ["analytics", "immunisation", since_days],
    queryFn: () =>
      apiRequest<ImmunisationCoverage[]>("/api/v1/analytics/immunisation-coverage", {
        query: { since_days },
      }),
  });
}

export function useStockOutRisk() {
  return useQuery({
    queryKey: ["analytics", "stock-out"],
    queryFn: () => apiRequest<StockOutRisk[]>("/api/v1/analytics/stock-out-risk"),
  });
}
