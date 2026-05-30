/**
 * LOINC code constants for vital-sign observations.
 *
 * Used by the worker encounter form so every captured vital carries a
 * stable terminology binding — this is what makes the FHIR Observation
 * export from `/fhir/Observation` resolvable by downstream systems
 * (DHIS2, HMIS, partner EMRs).
 *
 * Codes are sourced from LOINC ANSWERS + the FHIR Vital Signs IG.
 */

export const LOINC_SYSTEM = "http://loinc.org" as const;

export interface VitalCode {
  code: string;
  display: string;
  unit?: string;
  kind: "quantity" | "string";
  min?: number;
  max?: number;
  hint?: string;
}

export const VITAL_CODES = {
  TEMPERATURE: {
    code: "8310-5",
    display: "Body temperature",
    unit: "Cel",
    kind: "quantity",
    min: 30,
    max: 45,
    hint: "Tympanic / oral. Normal 36.5-37.5°C.",
  },
  BLOOD_PRESSURE: {
    code: "55284-4",
    display: "Blood pressure",
    kind: "string",
    hint: "Format: systolic/diastolic, e.g. 120/80.",
  },
  WEIGHT: {
    code: "29463-7",
    display: "Body weight",
    unit: "kg",
    kind: "quantity",
    min: 0,
    max: 250,
  },
  HEIGHT: {
    code: "8302-2",
    display: "Body height",
    unit: "cm",
    kind: "quantity",
    min: 30,
    max: 230,
  },
  PULSE: {
    code: "8867-4",
    display: "Heart rate",
    unit: "/min",
    kind: "quantity",
    min: 30,
    max: 220,
  },
  OXYGEN_SAT: {
    code: "59408-5",
    display: "Oxygen saturation",
    unit: "%",
    kind: "quantity",
    min: 50,
    max: 100,
  },
  RESPIRATORY_RATE: {
    code: "9279-1",
    display: "Respiratory rate",
    unit: "/min",
    kind: "quantity",
    min: 5,
    max: 60,
  },
} as const satisfies Record<string, VitalCode>;

export type VitalKey = keyof typeof VITAL_CODES;
