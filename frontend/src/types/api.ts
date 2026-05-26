/**
 * Wire-format type definitions. These mirror the FastAPI Pydantic models.
 * Keep them in sync with backend/app/schemas/* — manually for now; a future
 * iteration can codegen these from the OpenAPI document at /openapi.json.
 */

export type Role =
  | "citizen"
  | "worker"
  | "pharmacist"
  | "district_admin"
  | "ministry_admin";

export type Gender = "male" | "female" | "other" | "unknown";

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  role: Role;
  subject: string;
  name: string | null;
  facility_id: string | null;
};

// ── Patient ──────────────────────────────────────────────────────────────────

export type PatientCreate = {
  nin: string;
  given_name: string;
  family_name: string;
  gender: Gender;
  birth_date: string;
  phone?: string | null;
  email?: string | null;
  district: string;
  sub_county?: string | null;
  parish?: string | null;
  village?: string | null;
  consent_to_share?: boolean;
};

export type PatientOut = PatientCreate & {
  id: string;
  created_at: string;
  updated_at: string;
  deceased: boolean;
  record_version: number;
};

export type PatientSummary = {
  id: string;
  nin: string;
  given_name: string;
  family_name: string;
  gender: Gender;
  birth_date: string;
  district: string;
};

export type PaginatedPatients = {
  items: PatientSummary[];
  total: number;
  page: number;
  page_size: number;
};

// ── Encounter ────────────────────────────────────────────────────────────────

export type ObservationIn = {
  code_system: string;
  code: string;
  display?: string | null;
  value_quantity?: number | null;
  value_unit?: string | null;
  value_string?: string | null;
  effective_at: string;
};

export type ObservationOut = ObservationIn & {
  id: string;
  encounter_id: string;
  patient_id: string;
  recorded_by?: string | null;
};

export type EncounterCreate = {
  patient_id: string;
  facility_id: string;
  reason: string;
  started_at: string;
  ended_at?: string | null;
  observations?: ObservationIn[];
  diagnosis_codes?: string[];
};

export type EncounterOut = {
  id: string;
  patient_id: string;
  facility_id: string;
  reason: string;
  status: string;
  started_at: string;
  ended_at?: string | null;
  diagnosis_codes: string[];
  observations: ObservationOut[];
  created_at: string;
};

// ── Facility ─────────────────────────────────────────────────────────────────

export type FacilityOut = {
  id: string;
  code: string;
  name: string;
  level: string;
  district: string;
  sub_county: string | null;
  latitude: number | null;
  longitude: number | null;
};

// ── Supply ───────────────────────────────────────────────────────────────────

export type SupplyItemOut = {
  id: string;
  code: string;
  name: string;
  category: "medicine" | "vaccine" | "consumable" | "equipment" | "reagent";
  unit: string;
  reorder_threshold: number;
  requires_cold_chain: boolean;
  on_hand_total: number;
  facilities_stocked: number;
};

export type FacilityStockSnapshot = {
  facility_id: string;
  facility_name: string;
  item_code: string;
  item_name: string;
  on_hand: number;
  reorder_threshold: number;
  earliest_expiry: string | null;
  is_below_threshold: boolean;
};

export type StockTransferCreate = {
  from_facility_id: string;
  to_facility_id: string;
  supply_item_id: string;
  quantity: number;
  reason: string;
};

export type StockTransferOut = StockTransferCreate & {
  id: string;
  status: "in-progress" | "completed" | "abandoned";
  initiated_by: string;
  initiated_at: string;
  completed_at: string | null;
};

// ── Analytics ────────────────────────────────────────────────────────────────

export type DistrictEncounterCount = {
  district: string;
  encounter_count: number;
  patient_count: number;
};

export type ImmunisationCoverage = {
  district: string;
  antigen: string;
  doses_administered: number;
};

export type StockOutRisk = {
  facility_id: string;
  facility_name: string;
  district: string;
  item_code: string;
  item_name: string;
  on_hand: number;
  reorder_threshold: number;
  days_of_cover_estimated: number | null;
};

// ── Consent ──────────────────────────────────────────────────────────────────

export type ConsentScope =
  | "share_records_across_facilities"
  | "share_with_district_health_office"
  | "share_with_research"
  | "share_with_emergency_services";

export type ConsentOut = {
  id: string;
  patient_id: string;
  scope: ConsentScope;
  purpose: string;
  granted_at: string;
  expires_at: string | null;
  revoked_at: string | null;
};

export type OwnConsentGrant = {
  scope: ConsentScope;
  purpose: string;
  expires_at?: string | null;
};

// ── Me (self-serve) ──────────────────────────────────────────────────────────

export type ImmunisationOut = {
  id: string;
  encounter_id: string;
  patient_id: string;
  code_system: string;
  code: string;
  display: string | null;
  administered_at: string;
  facility_id: string | null;
};

export type AuditEntryOut = {
  id: string;
  actor_role: string;
  actor_facility_id: string | null;
  action: string;
  purpose: string | null;
  resource_type: string;
  resource_id: string;
  consent_id: string | null;
  occurred_at: string;
};

export type ProfileUpdate = {
  phone?: string | null;
  email?: string | null;
  sub_county?: string | null;
  parish?: string | null;
  village?: string | null;
};

// ── Staff self-serve + worker workflows ──────────────────────────────────────

export type StaffMeOut = {
  user_id: string;
  username: string;
  full_name: string;
  role: Role;
  facility_id: string | null;
  facility_name: string | null;
  facility_level: string | null;
  facility_district: string | null;
  active: boolean;
};

export type MarkDeceasedBody = {
  deceased: boolean;
  purpose?: string | null;
};

export type FacilityEncounterCount = {
  facility_id: string;
  facility_name: string;
  district: string;
  encounter_count: number;
  patient_count: number;
};

export type ReceiveStockBody = {
  supply_item_id: string;
  facility_id: string;
  lot_number: string;
  quantity: number;
  expires_on: string;        // YYYY-MM-DD
  received_on: string;       // YYYY-MM-DD
  cost_ugx?: number | null;
};

export type DispenseQuery = {
  supply_item_id: string;
  facility_id: string;
  quantity: number;
  encounter_id?: string | null;
  patient_id?: string | null;
  purpose?: string;
};

export type DispenseResult = {
  dispensed_quantity: number;
  events_recorded: number;
};

// ── Immunisation schedule + family ───────────────────────────────────────────

export type ImmunisationStatusLevel =
  | "complete"
  | "due"
  | "due-soon"
  | "overdue"
  | "not-yet";

export type AntigenStatusOut = {
  antigen: string;            // short label "BCG", "DPT", …
  display: string;            // human readable
  snomed_code: string;
  series_size: number;
  doses_given: number;
  next_dose_number: number | null;
  next_due_date: string | null;    // ISO date
  overdue_days: number;
  last_dose_at: string | null;
  status: ImmunisationStatusLevel;
};

export type CaregiverRelationship =
  | "mother"
  | "father"
  | "guardian"
  | "grandparent"
  | "sibling"
  | "aunt"
  | "uncle"
  | "other";

export type FamilyMemberOut = {
  link_id: string;
  patient_id: string;
  nin: string;
  given_name: string;
  family_name: string;
  birth_date: string;
  gender: Gender;
  relationship: string;
  overdue_antigen_count: number;
};

export type CaregiverLinkIn = {
  caregiver_nin: string;
  relationship: CaregiverRelationship;
};

export type CaregiverLinkOut = {
  id: string;
  caregiver_id: string;
  child_id: string;
  relationship: string;
  created_at: string;
};
