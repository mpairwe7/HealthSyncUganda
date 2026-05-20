# HealthSync Uganda — Design System

**Version:** 1.0 · **Owner:** Design + Frontend leads · **Status:** Accepted, governs the showcase build (25 June 2026)

The HealthSync Uganda design system encodes a visual language that is **trustworthy, calm, official, and clinically legible**. It draws on the visual conventions of Ugandan government digital services (deep green, white space, clear hierarchy) while meeting the specific demands of health information: dense data, long reading sessions, gloved hands on touchscreens, and low-bandwidth networks.

---

## 0. Design principles

These five principles overrule any individual rule below when they conflict:

1. **Patient safety before delight.** If a visual flourish risks misreading clinical data, it loses.
2. **Calm under pressure.** The interface should *reduce* the cognitive load of a nurse seeing 60 patients per day, not add to it.
3. **Official, not corporate.** This is government infrastructure. Visual language signals public trust, not startup energy.
4. **Legible at arm's length.** On a tablet on a desk, on a phone in poor light, indoors in the dry season — clinical type must read instantly.
5. **Local, not localised.** Luganda, Runyankole and Luo are first-class. Iconography respects Ugandan health-system conventions (HC II → NRH ladder, EPI antigen names, EMHSLU drug codes).

---

## 1. Colour palette

### 1.1 Brand colours

The palette is anchored on **deep green** — the colour of the Government of Uganda's digital services, the National Coat of Arms, and the Ministry of Health's published identity — paired with a clinical neutral and a single warm accent for citizen-facing surfaces.

| Token              | HEX       | Role                                                                                              |
| ------------------ | --------- | ------------------------------------------------------------------------------------------------- |
| `--brand-primary`  | `#0F5132` | **Primary action, headers, focus rings.** Deep, official green. Inspired by the Uganda Coat of Arms and `gov.ug` services. |
| `--brand-primary-700` | `#0A3D26` | Hover/pressed state on primary buttons.                                                        |
| `--brand-primary-100` | `#D7EAE0` | Soft tints — selected rows, active tab backgrounds, success surfaces.                          |
| `--brand-accent`   | `#C5A572` | **Honour accent** — used sparingly for citizen-facing achievements (immunisation badge, consent affirmations). Drawn from the gold/wheat tones in Uganda's flag and emblems. |
| `--brand-deep`     | `#0B1F33` | Worker/admin chrome, sidebars, ministry analytics — formal, low-glare.                          |

> *Why deep green not Pantone health-blue?* The conventional medical-blue palette is over-used worldwide and reads as commercial software. Deep green signals **public sector**, **Ugandan**, and **calm**. The healthcare register is preserved by neutrals + semantic colours below — not by hue.

### 1.2 Neutrals (surface scale)

| Token             | HEX       | Role                                                              |
| ----------------- | --------- | ----------------------------------------------------------------- |
| `--surface-0`     | `#FFFFFF` | Page background (citizen) / card surface (worker).                |
| `--surface-50`    | `#F7F8F6` | Page background (worker).                                         |
| `--surface-100`   | `#EEF1ED` | Subtle row striping in tables.                                    |
| `--surface-200`   | `#DCE2DC` | Borders, dividers.                                                |
| `--surface-700`   | `#3F4A40` | Secondary text on light surfaces.                                 |
| `--surface-900`   | `#0E1410` | Primary text on light surfaces.                                   |
| `--surface-inverse` | `#0B1F33` | Inverse surfaces (sidebars, admin chrome).                      |

### 1.3 Semantic colours

Used for **status, alerts, and clinical state**. These are reserved — never used decoratively.

| Token              | HEX       | Meaning                                                                                          |
| ------------------ | --------- | ------------------------------------------------------------------------------------------------ |
| `--state-success`  | `#2E7D5A` | "Saved", "Synced", "Up-to-date immunisation".                                                    |
| `--state-info`     | `#1F6FB2` | Neutral informational state, FHIR sync icons.                                                    |
| `--state-warning`  | `#B5651D` | Approaching stock-out, pending sync (offline queue), expiring item within 30 days.               |
| `--state-danger`   | `#9B1C1C` | Stock-out, critical vital, breaker tripped, denied consent attempt.                              |
| `--state-neutral`  | `#586256` | "No data", "Unknown".                                                                            |

Each semantic colour has a corresponding 100-tint for backgrounds (e.g. `--state-warning-100: #FCEDDE`) and a 700-shade for icon contrast.

**Rule:** never communicate status with colour alone. Pair every semantic colour with an icon **and** a text label. This is enforced by the `<StatusBadge>` and `<StockState>` components.

### 1.4 Dark mode (admin / ministry)

The ministry analytics view ships a **calm dark theme** by default — large operations rooms with projectors benefit from it. The palette inverts to:

| Token             | Dark value | Notes                                                |
| ----------------- | ---------- | ---------------------------------------------------- |
| `--surface-0`     | `#0B1F33`  | Page background.                                     |
| `--surface-50`    | `#10283E`  | Card surface.                                        |
| `--surface-900`   | `#E8EEEA`  | Primary text.                                        |
| `--brand-primary` | `#5FB48A`  | Lifted green that meets contrast on the dark canvas. |

All semantic colours also have dark-mode pairs that meet WCAG 2.2 AA.

---

## 2. Typography

### 2.1 Type families

| Role               | Family                         | Why                                                                                                                                                                |
| ------------------ | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **UI / text**      | **Inter** (variable)           | Open-source, hinted at small sizes, screen-optimised. Strong cross-language support, including the diacritics needed for Luganda and Runyankole. Apache-2.0 OFL.   |
| **Headings**       | **Inter Display**              | Same family, optical-size 24+. Avoids the cost of a second font load on slow networks.                                                                             |
| **Monospace**      | **JetBrains Mono**             | NIN strings, batch numbers, FHIR identifiers, X-Trace-Id. Disambiguates 0/O, 1/I/l.                                                                                |

We deliberately do **not** ship a "branded" display face. Health data is the brand; the type should disappear.

Inter is fetched self-hosted (no Google Fonts call) so the platform works behind firewalls and on the rural offline scenario.

### 2.2 Scale

Modular scale ratio **1.200 ("minor third")** — a quiet, conservative ratio that suits dense clinical data.

| Token         | Size (rem) | Px @ 16 root | Use                                              |
| ------------- | ---------- | ------------ | ------------------------------------------------ |
| `--text-xs`   | 0.75       | 12           | Legal footers, tertiary metadata.                |
| `--text-sm`   | 0.875      | 14           | Table cells, secondary labels.                   |
| `--text-base` | 1.000      | 16           | **Default body. Never go smaller for clinical content.** |
| `--text-lg`   | 1.125      | 18           | Form labels, citizen-portal body.                |
| `--text-xl`   | 1.250      | 20           | Card titles.                                     |
| `--text-2xl`  | 1.500      | 24           | Page titles (admin/worker).                      |
| `--text-3xl`  | 1.875      | 30           | Citizen welcome screen, dashboards.              |
| `--text-4xl`  | 2.250      | 36           | Landing hero.                                    |

### 2.3 Weight, line-height, tracking

| Style       | Weight | Line-height | Tracking | Notes                                                                          |
| ----------- | ------ | ----------- | -------- | ------------------------------------------------------------------------------ |
| Display     | 700    | 1.10        | -0.02em  | Hero, citizen welcome.                                                         |
| Title       | 600    | 1.25        | -0.01em  | Page and card titles.                                                          |
| Body        | 400    | 1.55        | 0        | Default reading text.                                                          |
| Strong body | 600    | 1.55        | 0        | Inline emphasis on clinical fields (drug name, dosage).                        |
| Caption     | 400    | 1.40        | 0        | Helper text, footnotes.                                                        |
| Mono        | 500    | 1.30        | 0        | Identifiers, codes.                                                            |

**Clinical reading rule:** body line-length is capped at **70 characters** in long-form views (citizen records, history). Wider lines become illegible in fatigue.

### 2.4 Multilingual considerations

- Luganda and Runyankole strings can run **40-60 % longer** than English. UI containers must wrap, not truncate, by default. `<Truncate>` is opt-in and accompanied by a tooltip.
- Word breaks inside long Luganda compounds (e.g. *"Akakode ak'omulundi gumu"*) prefer `overflow-wrap: anywhere` over hyphenation.
- Avoid ALL-CAPS for non-English strings — Bantu morphology relies on word shape that all-caps destroys.

---

## 3. Spacing & layout

### 3.1 Spacing scale

Base unit: **4 px**. All spacing is a multiple of base — this gives the calm rhythm that government documents have.

| Token       | px  |                                                  |
| ----------- | --- | ------------------------------------------------ |
| `--space-1` | 4   | icon-to-text gap                                 |
| `--space-2` | 8   | dense control padding                            |
| `--space-3` | 12  | input vertical padding                           |
| `--space-4` | 16  | **default card inner padding**                   |
| `--space-5` | 20  | between adjacent cards                           |
| `--space-6` | 24  | section internal padding                         |
| `--space-8` | 32  | between major sections on a dashboard            |
| `--space-10`| 40  | page top padding (worker)                        |
| `--space-12`| 48  | landing hero outer padding                       |

### 3.2 Grid + breakpoints

| Breakpoint | Min width | Use case                                                                       |
| ---------- | --------- | ------------------------------------------------------------------------------ |
| `sm`       | 640 px    | Citizen phone, nurse smartphone.                                               |
| `md`       | 768 px    | HC III tablet (the dominant clinician device).                                 |
| `lg`       | 1024 px   | Pharmacist/laptop view, supply dashboards.                                     |
| `xl`       | 1280 px   | Ministry analytics, dual-monitor admin.                                        |
| `2xl`      | 1536 px   | Operations-room projector.                                                     |

Content max-width is **1280 px** with 24 px gutters; analytics dashboards opt into `1536 px` via `<WideContainer>`.

### 3.3 Density modes

The platform ships **two density modes** selectable in user preferences:

- **Comfort** (default for citizen, default for worker on touch devices) — row height 56 px, generous spacing.
- **Compact** (default for ministry/admin on desktop) — row height 40 px, table-first.

Density is one CSS custom property — `--row-height` — so the same component renders both. There is no separate compact component set.

### 3.4 Layout templates

| Template            | Layout                                                                                         | Used by                       |
| ------------------- | ---------------------------------------------------------------------------------------------- | ----------------------------- |
| `MarketingShell`    | Centered hero + 3-up cards, white background.                                                  | `/` landing.                  |
| `CitizenShell`      | Sticky header, full-width cards, single column on mobile, 2-column on tablet+.                 | Citizen portal.               |
| `WorkerShell`       | Left sidebar (collapsible to icons), main content, sticky action bar on mobile.                | Worker, pharmacist.           |
| `AdminShell`        | Left rail + top tabs, dark chrome, dense tables, charts on the right.                          | District + Ministry analytics. |

All shells include the **`<SyncIndicator />` + `<LocaleSwitcher />`** in the header — they are not optional.

---

## 4. Components

The full Storybook lives at `frontend/storybook` (post-pilot). Below are the component contracts that govern the showcase build.

### 4.1 Buttons

| Variant      | Background          | Text         | Border         | When to use                                            |
| ------------ | ------------------- | ------------ | -------------- | ------------------------------------------------------ |
| `primary`    | `--brand-primary`   | `#FFFFFF`    | none           | Main action per surface — at most one per view.        |
| `secondary`  | `#FFFFFF`           | `--brand-primary` | `--brand-primary` | Adjacent supporting action.                            |
| `ghost`      | transparent         | `--surface-900` | none           | Tertiary, in dense toolbars.                           |
| `destructive`| `--state-danger`    | `#FFFFFF`    | none           | Revoke consent, delete draft. Always second-click confirm. |
| `link`       | transparent         | `--brand-primary` | underline-on-hover | Inline navigation.                                     |

**Sizes:** `sm` (32 px), `md` (40 px, default), `lg` (48 px touch). Touch targets never go below 44 × 44 px (WCAG 2.5.5).

**Loading state:** a left-aligned spinner replaces the leading icon; the label changes to the *-ing* present continuous (e.g. *"Verifying…"*) — this matches the i18n contract that requires translatable verbs.

### 4.2 Forms

- Labels above inputs, never floating. Floating labels confuse screen readers and break in Luganda where the placeholder text is wider than the input.
- Required fields marked with `(required)` text, not `*` alone. `*` is ambiguous in clinical settings.
- Error text in `--state-danger`, paired with an inline `AlertCircle` icon and an `aria-describedby` link to the input.
- One question per row on mobile; on desktop, related fields may share a row when the relationship is explicit (first/last name, systolic/diastolic).
- **Input metric chips** beside numeric vitals — small grey pills showing the unit (mmHg, kg, °C, /min). Reduces unit-confusion incidents.

### 4.3 Patient cards

The atomic clinical primitive. Always shows in this order, top to bottom:

1. **Identity strip** — full name (largest), preferred name in parentheses if different, sex/age, NIN (monospace, masked except last 4 digits unless user opts in).
2. **Risk row** — chips for allergies, chronic conditions, current pregnancy (if applicable). High-contrast against the card surface.
3. **Last encounter** — date, facility name, presenting complaint.
4. **Actions** — *Open record* (primary), *New encounter* (secondary), *Share via referral* (link).

Never put a photo on the patient card by default; opt-in only, and stored as a separate FHIR `Patient.photo` field that the citizen can disable in their consent centre.

### 4.4 Tables

Tables are the most-used pattern. They follow these rules:

- **Sticky header.** On long tables, the header row sticks at the top of the scroll container.
- **Right-align numbers, left-align text, centre-align icons.** No exceptions.
- **Tabular numerals.** `font-variant-numeric: tabular-nums` so columns of numbers line up.
- **Row hover** uses `--surface-100`, never primary green — green-hover on every row reads as "selected".
- **Selection** uses a left edge accent stripe in `--brand-primary` + a single highlight row. Multi-select shows a sticky toolbar above.
- **Empty states** are never blank: an illustration-free placeholder plus a one-sentence next-step ("No encounters yet — open the patient record to add one").
- **Pagination** over infinite scroll for clinical tables — clinicians need to know where they are.

### 4.5 Status indicators

Five reserved patterns, each is a `<StatusBadge>` component:

| Pattern                | Glyph                          | Colour token          |
| ---------------------- | ------------------------------ | --------------------- |
| Synced                 | check inside a circle          | `--state-success`     |
| Pending sync           | clock                          | `--state-warning`     |
| Sync failed            | exclamation in triangle        | `--state-danger`      |
| Stock OK / Above       | upward arrow                   | `--state-success`     |
| Low / approaching      | minus inside circle            | `--state-warning`     |
| Stock-out              | X inside circle                | `--state-danger`      |
| Breaker open           | broken circuit icon            | `--state-danger`      |
| Breaker half-open      | dashed circuit icon            | `--state-warning`     |

### 4.6 Interoperability badges

Health-data exchange needs **visible provenance**. Every imported or shared record carries a "data passport" chip:

```
[ FHIR R4 ] [ NIRA-verified ] [ DHIS2 synced ] [ Last sync 12:04 ]
```

- The FHIR R4 chip is `--brand-deep` background, white text, monospace label.
- "Source-of-truth" badges are `--state-success` outline-only — they don't shout.
- Tapping a chip opens the **provenance drawer** showing the FHIR `meta.source`, `meta.lastUpdated`, and a link to the audit log entry. This drawer is the same component across worker, citizen, and ministry views.

### 4.7 Supply-chain tracking

Supply visualisation has its own micro-system because the data shapes are unique:

- **Stock gauge** — a horizontal bar with three zones (red ≤ threshold, amber ≤ 1.5× threshold, green above). The threshold line is always drawn, even when stock is comfortable, so the clinician sees the safety margin.
- **Expiry timeline** — a horizontal time strip; expired stock is hatched, not just red, so colour-blind users still see it.
- **Ledger entry chip** — every transfer card carries the hash-chain link icon plus a short hash prefix (`#a8c3…`) that opens the ledger verification panel.

---

## 5. Project-specific design recommendations

### 5.1 Citizen vs Healthcare-worker visual differentiation

The two audiences need to *feel* different the moment they sign in.

| Dimension              | Citizen view                                          | Worker view                                              |
| ---------------------- | ----------------------------------------------------- | -------------------------------------------------------- |
| Page background        | `--surface-0` (white)                                 | `--surface-50` (warm off-white)                          |
| Type scale             | One step larger across the board                      | Default                                                  |
| Density                | Comfort only                                          | Comfort + Compact toggle                                 |
| Navigation             | Bottom tab bar on mobile, large tiles                 | Left sidebar, top breadcrumbs                            |
| Accent usage           | More `--brand-accent` (achievements, badges)          | Almost never; honour accent is reserved for citizens     |
| Imagery                | Tiles use simple line illustrations of facilities, vaccines, family — Ugandan-styled, not Western clipart | Iconography only — no decorative imagery |
| Voice                  | Direct: "You", "Your record", "We sent you an OTP"    | Clinical: "Patient", "Encounter", "Last vitals"          |

### 5.2 Patient record, referral, and medicine flows

**Patient record** uses a **vertical timeline** of encounters with sticky date headers (Today / This week / Earlier). Each encounter card is collapsible; the diagnosis, prescriptions and observations are nested. This is the most-clicked page in the app and we optimise for *quick scan, deep dive on demand*.

**Referrals** are a distinct visual pattern: a referral is shown as a **journey strip** between two facility chips, with the status (`Requested → Accepted → Patient seen → Closed`) as a four-stop progress meter. The receiving facility appears in a different colour family so it is unambiguous "where the patient is going".

**Medicine tracking** uses the same vocabulary at two scales:
- *Patient prescription*: drug name (strong body), dose (mono), schedule (caption), with the EMHSLU code in the provenance drawer.
- *Facility stock*: same drug name in the same weight, paired with the stock gauge described above. The deliberate visual rhyme tells the pharmacist "this prescription draws on that stock".

### 5.3 FHIR interoperability — visual language

Interoperability is invisible most of the time; it surfaces in three specific places:

1. **Provenance drawer** (described above). The single source of truth for "where did this datum come from?".
2. **Sync indicator** in the header — always shows online/offline state and pending-mutation count. Tapping it opens the queue with each mutation's idempotency key and target endpoint.
3. **Resilience strip** on admin dashboards — small live tiles for each external dependency (NIRA, DHIS2, Redis, Postgres) showing breaker state. This is the *one place* we use semantic colour to drive attention; everywhere else, colour follows data.

The visual rule: **interoperability is reassurance, not noise.** Citizens see "Your record is shared across X facilities" once, not on every page.

---

## 6. Accessibility & mobile-first

### 6.1 WCAG conformance target

We target **WCAG 2.2 AA**, with three AAA criteria adopted because of the clinical context:

- **1.4.6** Enhanced contrast (7:1) for all clinical text (drug names, dosages, allergies). The general UI meets 4.5:1.
- **2.5.5** Target size 44 × 44 px minimum on all interactive elements.
- **3.3.4** Error prevention on irreversible clinical actions (consent revocation, supply transfer commit).

### 6.2 Specific affordances

- **Focus rings** — 2 px solid `--brand-primary` with a 2 px outer halo of `--surface-0`, always visible (no `:focus-visible` only — many clinicians use keyboards because of gloves).
- **Skip link** at the top of every page, jumping to main content. Translates.
- **Reduced motion** — every animation is gated on `prefers-reduced-motion`. The sync indicator collapses from a subtle pulse to a static badge.
- **Right-to-left** is not in scope for the launch but the design tokens (logical spacing) are RTL-safe for future expansion.
- **Glove-friendly hit areas** — paired with `touch-action: manipulation` to suppress the 300 ms tap delay on Android Chromium.
- **Screen reader labels** — every icon-only button carries an `aria-label` that is part of the i18n dictionary.

### 6.3 Low-connectivity / low-power adaptations

- **System font fallback** kicks in instantly while Inter loads. Layout is identical because the metrics are matched.
- **Image budget** — every page ships fewer than 50 KB of imagery on the critical path. Photos are progressive JPEGs with `loading="lazy"`.
- **Skeletons over spinners** — a layout shimmer reassures the user that something is coming, where a spinner suggests it might never.
- **Offline-first UI states** — every page has a defined "offline" treatment; no empty states with "Failed to load". The data either comes from cache or surfaces with a "showing last sync at 12:04" banner.
- **Battery & data saver** — when `Save-Data: on` is reported, animations stop and analytics tiles render as numbers instead of sparklines.
- **Print stylesheet** — discharge summaries and referrals print cleanly on A4 with no chrome. This still matters; many clinics need paper for handovers.

---

## 7. Tokens & implementation

The system ships as a single CSS variable set in `frontend/src/app/globals.css`, plus a Tailwind theme extension that surfaces every token as a utility class. Components import semantic tokens only (`bg-primary`, `text-success`), never raw hexes.

```css
:root {
  --brand-primary: #0F5132;
  --brand-primary-700: #0A3D26;
  --brand-primary-100: #D7EAE0;
  --brand-accent: #C5A572;
  --brand-deep: #0B1F33;
  --surface-0: #FFFFFF;
  --surface-50: #F7F8F6;
  --surface-100: #EEF1ED;
  --surface-200: #DCE2DC;
  --surface-700: #3F4A40;
  --surface-900: #0E1410;
  --state-success: #2E7D5A;
  --state-info:    #1F6FB2;
  --state-warning: #B5651D;
  --state-danger:  #9B1C1C;
  --state-neutral: #586256;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
  --radius-pill: 9999px;
  --shadow-1: 0 1px 2px rgba(14,20,16,.06);
  --shadow-2: 0 4px 12px rgba(14,20,16,.08);
  --row-height: 56px;
}
```

A token diff against the showcase build is in `docs/DESIGN_TOKENS_CHANGELOG.md` (forthcoming).

---

## 8. Alignment with Ugandan government digital identity

How this system stays in sync with the broader `gov.ug` family **without** becoming a clone:

- **Primary green** is drawn directly from the palette used across `health.go.ug`, `nira.go.ug`, and `nita.go.ug`. The exact hex is tuned (slightly darker, slightly less saturated) to meet 7:1 contrast for clinical text — a deliberate, documented deviation that any government design reviewer will accept on accessibility grounds.
- **Sans-serif body, sober proportions, generous whitespace.** This mirrors the Government Communications Department's published web guidance.
- **Coat-of-Arms / National emblem usage** — we do not use the Coat of Arms inside the product UI (only in printable documents like discharge summaries, where it appears in the footer once, in greyscale, per the Office of the President's guidance). This avoids the "imitation officialdom" trap.
- **The accent gold (`#C5A572`)** is a low-saturation interpretation of the wheat/gold tones in the national emblem. It signals warmth on citizen-facing surfaces *without* being a flag-reference.
- **No partisan iconography, no regional colours**, no imagery that could be read as favouring one community. Iconography is universally Ugandan: line drawings of HC III facility shapes, EPI antigen vials, and motherhood-and-child silhouettes rendered in the same line weight.
- **Voice** matches the formal, present-tense register of Ministry communications — direct but never breezy. We avoid contractions in clinical microcopy ("Cannot complete", not "Can't complete"), but allow contractions in citizen-facing strings where the reading age target is lower.

### Where the system intentionally departs from typical government UI

| Convention                                       | What we do                                            | Why                                            |
| ------------------------------------------------ | ----------------------------------------------------- | ---------------------------------------------- |
| Dense PDFs and tables                            | Cards-first on mobile, tables on desktop only        | Clinicians work on tablets, not laptops.       |
| Centered "stamp-style" headers                    | Left-aligned, sticky                                  | Better scanning at speed.                       |
| Heavy use of headers + sub-headers in caps        | Sentence case throughout                              | Higher reading speed; Luganda incompatibility.  |
| External links opening in new tabs by default     | Same-tab navigation, except auditable destinations    | Less context-switching for clinical workflows.  |

---

## 9. Open questions for review

- **Storybook** — to ship post-pilot; the Innovator Registry build does not require it.
- **Pictogram set** — the team is commissioning a Ugandan illustrator (see `docs/TEAM.md`) for the citizen tile illustrations. Until then, lucide-react glyphs in `--brand-primary` are used.
- **Print stylesheet for referrals** — drafted, needs a clinical sign-off from the Lacor referral coordinator before pilot.
- **High-contrast theme** — there is a "high-contrast" toggle planned for visually impaired clinicians; tokens are ready, switcher UI is not.

This document is the source of truth for visual decisions and supersedes ad-hoc Figma frames. Material change to a token requires an ADR (see `docs/adr/`).
