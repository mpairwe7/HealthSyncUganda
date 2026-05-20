/**
 * Translation dictionaries. Lightweight on purpose — no runtime dependency.
 *
 * Add a new locale by adding a key under `dictionaries` and translating every
 * key in `en`. TypeScript will fail the build if any key is missing.
 */

const enRaw = {
  appName: "HealthSync Uganda",
  // Locales — labels shown in the language picker (in their own language)
  locales: {
    en: "English",
    lg: "Luganda",
  },
  // Header
  nav: {
    citizenRecords: "My records",
    workerDashboard: "Worker dashboard",
    administration: "Administration",
    signOut: "Sign out",
  },
  online: {
    online: "Online",
    offline: "Offline",
    pending: (n: number) => `${n} pending`,
    syncNow: "Sync now",
  },
  // Landing
  landing: {
    eyebrow: "HealthSync Uganda",
    heading: "One record. Every facility. Even offline.",
    sub:
      "A FHIR R4-compliant national digital health backbone linking citizens to their records, ministries to their data, and supply chains to the last health centre — designed for Uganda's networks and Uganda's clinicians.",
    ctaCitizen: "Citizen sign-in (NIN)",
    ctaWorker: "Healthcare worker sign-in",
    pillars: {
      nin: { title: "NIN-linked", desc: "One record per citizen, across every facility." },
      offline: { title: "Offline-first", desc: "Mutations sync when the network returns." },
      fhir: { title: "FHIR R4", desc: "Open standards, zero vendor lock-in." },
      supply: { title: "Supply visibility", desc: "Stock-outs, transfers and expiry tracked live." },
    },
    cards: {
      citizen: {
        title: "Citizen portal",
        desc: "View your health record, manage consent, find facilities, book appointments.",
      },
      worker: {
        title: "Healthcare worker",
        desc: "Record encounters, check vitals, file prescriptions — even offline.",
      },
      admin: {
        title: "Ministry & district",
        desc: "Watch immunisation coverage, stock-out risk and audit access across the network.",
      },
    },
    open: "Open",
  },
  // Citizen sign-in
  citizenLogin: {
    title: "Citizen sign-in",
    description:
      "Verify with your National Identification Number (NIN) and the one-time password sent to your registered phone.",
    ninLabel: "National Identification Number (NIN)",
    ninHelp: "14 characters. Find it on the back of your National ID card.",
    otpLabel: "One-time password",
    otpHelpDemo: "Demo OTP:",
    otpHelpReal: "Production uses NIRA-issued OTPs.",
    submit: "Sign in",
    submitting: "Verifying…",
    welcome: (name: string) => `Welcome, ${name}`,
    audit:
      "Your record is encrypted in transit. Every access is logged in an immutable audit trail you can review under Access history.",
    nin404: "NIN not found at NIRA",
    badOtp: "Invalid OTP",
  },
  // Citizen home tiles
  citizenHome: {
    welcomeFallback: "citizen",
    welcome: (name: string) => `Welcome, ${name}`,
    sub: "Your health record is yours. View it, share it, and revoke access — anytime.",
    tiles: {
      records: {
        title: "My records",
        desc: "Encounters, vitals, immunisations across every facility you've visited.",
      },
      consent: {
        title: "Consent centre",
        desc: "Decide which facilities and programs can access your record.",
      },
      immunisations: {
        title: "Immunisations",
        desc: "Vaccines you've received and reminders for upcoming doses.",
      },
      appointments: {
        title: "Appointments",
        desc: "Book and manage upcoming visits at any facility.",
      },
      facilities: {
        title: "Find a facility",
        desc: "Locate the nearest accredited health centre, with directions.",
      },
    },
    open: "Open",
  },
};

type Dictionary = typeof enRaw;
export const en: Dictionary = enRaw;

/**
 * Luganda translation of the citizen-facing strings.
 *
 * Notes for the translator:
 * - These strings are reviewed by a native Luganda speaker before pilot.
 * - The `welcome(name)` callbacks must keep the `${name}` placeholder.
 * - Clinical jargon (e.g. "NIN") is kept verbatim because that is how it
 *   appears on the citizen's physical NIRA card.
 */
const lg: Dictionary = {
  appName: "HealthSync Uganda",
  locales: { en: "Olungereza", lg: "Oluganda" },
  nav: {
    citizenRecords: "Ebintu byange",
    workerDashboard: "Ekifo ky'omukozi",
    administration: "Obufuzi",
    signOut: "Vva ku akawunti",
  },
  online: {
    online: "Ku yintaneeti",
    offline: "Tewali yintaneeti",
    pending: (n: number) => `${n} bisigaddewo`,
    syncNow: "Sinkanya kati",
  },
  landing: {
    eyebrow: "HealthSync Uganda",
    heading: "Rikodi emu. Buli ddwaliro. Ne bw'oba tewali yintaneeti.",
    sub:
      "Olutindo lwa Uganda olw'obujjanjabi obw'omu kompyuta, olukwataganya buli mutuuze ne rikodi ze, ne Minisitule ku data zaayo, n'okusindika eddagala mu masuubuzi gonna — lwakolebwa olw'engeri ya yintaneeti ya Uganda n'abaganga ba Uganda.",
    ctaCitizen: "Yingira (NIN)",
    ctaWorker: "Yingira ng'omukozi ow'obujjanjabi",
    pillars: {
      nin: { title: "Yegattidwa ku NIN", desc: "Rikodi emu ku buli mutuuze, mu buli ddwaliro." },
      offline: {
        title: "Etandika nga tewali yintaneeti",
        desc: "Enkyukakyuka zigenda zikola yintaneeti bw'akomawo.",
      },
      fhir: { title: "FHIR R4", desc: "Engeri ezikkirizibwa wonna, tewali kuziyizibwa." },
      supply: {
        title: "Okulaba eddagala",
        desc: "Eddagala eriweddewo, okutambuza, n'okufa kw'eddagala bilondoolwa mu kiseera.",
      },
    },
    cards: {
      citizen: {
        title: "Ekifo ky'omutuuze",
        desc:
          "Laba rikodi yo ey'obujjanjabi, kulira okukkiriza, zuula amalwaliro, era teekateeka okukyala.",
      },
      worker: {
        title: "Omukozi w'obujjanjabi",
        desc:
          "Wandiika emikolo, kebera obulamu, gabira eddagala — ne bw'oba tewali yintaneeti.",
      },
      admin: {
        title: "Minisitule n'eddisitulikiti",
        desc:
          "Tunula obugagga bw'okugema, akabi k'eddagala okuggwaawo, n'okukebera enkozesa mu lutindo lwonna.",
      },
    },
    open: "Ggulawo",
  },
  citizenLogin: {
    title: "Yingira ng'omutuuze",
    description:
      "Wewuumiza ng'okozesa ennamba yo eya National Identification Number (NIN) n'akakode ak'omulundi gumu akaweereddwa ku ssimu yo eyaweerwa.",
    ninLabel: "Ennamba ya National Identification Number (NIN)",
    ninHelp: "Ennukuta 14. Ginoonye ku mabega wa kaadi yo ya National ID.",
    otpLabel: "Akakode ak'omulundi gumu",
    otpHelpDemo: "Akakode ak'okwoleka:",
    otpHelpReal: "Mu nkozesa ennamba, NIRA y'eweereza akakode.",
    submit: "Yingira",
    submitting: "Tukekkereza…",
    welcome: (name: string) => `Tukusanyukidde, ${name}`,
    audit:
      "Rikodi yo ekuumiddwa nga etambula. Buli kuyingira kuwandiikibwa mu rikodi etakyusibwa gy'osobola okutunula mu Ebyafaayo by'okuyingira.",
    nin404: "NIN tezuuliddwa ku NIRA",
    badOtp: "Akakode kakyamu",
  },
  citizenHome: {
    welcomeFallback: "mutuuze",
    welcome: (name: string) => `Tukusanyukidde, ${name}`,
    sub:
      "Rikodi yo ey'obujjanjabi yiyo. Gitunule, gigabe, era gisalemu — ekiseera kyonna.",
    tiles: {
      records: {
        title: "Ebintu byange",
        desc: "Emikolo, obulamu, n'okugema mu buli ddwaliro lye wakyalako.",
      },
      consent: {
        title: "Ekifo ky'okukkiriza",
        desc: "Salaawo amalwaliro n'engatto eziyinza okutunula ku rikodi yo.",
      },
      immunisations: {
        title: "Okugema",
        desc: "Eddagala ly'okukuumira lye wafuna n'okujjukiza okw'eddagala eddilala.",
      },
      appointments: {
        title: "Okukyala",
        desc: "Teekateeka era ddukanya okukyala kwo mu ddwaliro lyonna.",
      },
      facilities: {
        title: "Zuula ddwaliro",
        desc: "Zuula eddwaliro eriri okumpi ery'ekikkirizibwa, n'okusobozesebwa.",
      },
    },
    open: "Ggulawo",
  },
};

export const dictionaries = { en, lg } as const;
export type Locale = keyof typeof dictionaries;
export const LOCALES: Locale[] = ["en", "lg"];
