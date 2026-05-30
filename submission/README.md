# Submission packet — MoICT&NG Government Systems Prototype Showcase

**Submission date:** 25 May 2026
**Deadline:** 1 June 2026
**Thematic Area:** #3 — Health Information Systems

> This entire directory is **gitignored** by project policy. Files here exist only on the operator's local machine; copy them off (USB / email / cloud-share) when ready to submit.

## Contents (after running the build steps below)

```
submission/
├── README.md                                      ← this file
├── HealthSync-Uganda-System-Description.md        ← markdown source (~14 KB)
├── HealthSync-Uganda-System-Description.html      ← HTML companion (~17 KB)
├── HealthSync-Uganda-System-Description.pdf       ← rendered PDF (~41 KB, 4 pages A4)
├── diagrams/                                      ← Mermaid source files (.mmd)
│   ├── 01-c4-context.mmd
│   ├── 02-c4-container.mmd
│   ├── 03-resilience-flow.mmd
│   └── 04-security-boundaries.mmd
└── figures/                                       ← rendered PNGs (~60–130 KB each)
    ├── 01-c4-context.png
    ├── 02-c4-container.png
    ├── 03-resilience-flow.png
    ├── 04-security-boundaries.png
    ├── 05-worker-enrolment-offline.png            ← real UI screenshot (capture per §2)
    └── 06-citizen-audit-trail.png                 ← real UI screenshot (capture per §2)
```

Last rendered: 2026-05-28 via `weasyprint` (PDF) + `pypandoc` (DOCX) + `mmdc` (PNGs), per the recipes in §§3-4. The source markdown was refreshed for the compliance sweep (commits 5b386af..fa226a3 — facility-and-consent scoping at the access layer, Postgres append-only triggers, FHIR Encounter/Observation/Immunization/MedicationDispense, deleted seed-admin endpoint, AUTO_MIGRATE deploy hook, 44-test staging regression).

## Build

### 1. Render the Mermaid diagrams to PNG

The project's rendering rig of record is **`@mermaid-js/mermaid-cli` (`mmdc`)** invoked with a custom Puppeteer configuration. Two flags are non-negotiable in container / CI / VSCode-Server shells:

1. **`--no-sandbox` + `--disable-setuid-sandbox`** — most non-root shells don't have the user-namespace privileges Chromium expects.
2. **`--single-process`** — without this, mmdc 11.x dies with `ConnectionClosedError: Connection closed.` mid-render on the Crane Cloud / VSCode-Server environment. Confirmed empirically 2026-05-26.

A third flag — **`TMPDIR=$HOME/.cache/playwright-tmp`** — works around the same `EOPNOTSUPP` SingletonLock issue we hit in Playwright (NFS-backed `/tmp` doesn't support the lock semantics Chromium expects).

```bash
# One-off install
bun install -g @mermaid-js/mermaid-cli   # or: npm install -g @mermaid-js/mermaid-cli

# Puppeteer config — keep ALL five flags, they're each load-bearing
cat > /tmp/puppeteer-cfg.json <<'EOF'
{
  "args": [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--single-process"
  ]
}
EOF

# Workaround for NFS /tmp (skip if /tmp is local)
mkdir -p ~/.cache/playwright-tmp

# Render each diagram
cd submission
for fig in 01-c4-context 02-c4-container 03-resilience-flow 04-security-boundaries; do
  TMPDIR=$HOME/.cache/playwright-tmp \
    mmdc -i diagrams/${fig}.mmd \
         -o figures/${fig}.png \
         --backgroundColor white --scale 2 \
         --theme default \
         --puppeteerConfigFile /tmp/puppeteer-cfg.json
done
```

Output: 4 PNGs at 60-130 KB each (1920px wide at `--scale 2`).

> **Note on Mermaid syntax:** edge labels with `/` or `+` characters in dotted-arrow syntax (`-.label.->`) trip Mermaid 11.x's lexer. Quote them: `-. "label with / and +" .->`. The provided `01-c4-context.mmd` is already quoted.

If `mmdc` is unavailable, paste each `.mmd` file into <https://mermaid.live> and **Actions → Download PNG**.

### 2. Capture the UI screenshots (Figures 5 & 6)

```bash
make full        # or: docker compose --profile full up --build
```

- **Figure 5 — `05-worker-enrolment-offline.png`:** sign in as `nurse.gulu / demo1234` at <http://localhost:3000/login>. Open DevTools → Network → throttling → **Offline**. Navigate to "Enrol patient", fill in the form, submit. Screenshot the resulting toast *"Saved offline — will sync when network returns"* plus the header sync-indicator badge incremented to 1.
- **Figure 6 — `06-citizen-audit-trail.png`:** sign in at <http://localhost:3000/citizen/login> with NIN `CM85051712345X` / OTP `000000`. Navigate to `/citizen/records` and screenshot the audit-trail panel (actor, role, facility, purpose).

### 3. Convert the system description to PDF — **weasyprint path (no LaTeX needed)**

The project's PDF rendering uses **`weasyprint`** + Python's `markdown` library because it's pure-Python (no LaTeX install), reliable on minimal container images, and produces clean A4 output at a small file size.

```bash
cd <repo-root>

# One-off install if not present
pip install --user markdown weasyprint

python3 <<'PY'
import markdown
from weasyprint import HTML, CSS
from pathlib import Path

md = Path("submission/HealthSync-Uganda-System-Description.md").read_text()
body = markdown.markdown(
    md,
    extensions=["tables", "fenced_code", "attr_list"],
    output_format="html5",
)

# Tightened CSS to hit the 5-page A4 target; matches the Uganda
# government digital-identity green palette used by docs/DESIGN_SYSTEM.md.
css = CSS(string="""
  @page { size: A4; margin: 1.4cm 1.5cm; }
  body { font-family: "DejaVu Sans","Inter",sans-serif; font-size: 9pt; line-height: 1.25; color: #111; }
  h1 { font-size: 16pt; color: #0E5C39; margin: 0 0 0.3em 0; }
  h2 { font-size: 12.5pt; color: #0E5C39; margin: 0.9em 0 0.25em 0; page-break-after: avoid; }
  h3 { font-size: 10.5pt; color: #0E5C39; margin: 0.7em 0 0.2em 0; page-break-after: avoid; }
  p  { margin: 0.3em 0; }
  ul,ol { margin: 0.3em 0 0.5em 1.4em; padding: 0; }
  li { margin: 0.05em 0; }
  table { border-collapse: collapse; width: 100%; margin: 0.4em 0; font-size: 8pt; }
  th,td { border: 1px solid #ccc; padding: 2px 5px; text-align: left; vertical-align: top; }
  th { background: #F0F8F2; font-weight: bold; }
  code { font-family: "DejaVu Sans Mono",monospace; background: #f5f5f5; padding: 0 2px; font-size: 8pt; }
  pre  { background: #f5f5f5; padding: 4px 6px; border-left: 2px solid #0E5C39; font-size: 7.5pt; page-break-inside: avoid; }
  hr   { border: none; border-top: 1px solid #ccc; margin: 0.6em 0; }
  a    { color: #1A5490; text-decoration: none; }
  blockquote { border-left: 2px solid #0E5C39; padding-left: 6px; color: #444; font-style: italic; }
""")

pdf = HTML(string=f"<!doctype html><html><body>{body}</body></html>").render(stylesheets=[css])
pdf.write_pdf("submission/HealthSync-Uganda-System-Description.pdf")
print(f"  pages: {len(pdf.pages)}, file: submission/HealthSync-Uganda-System-Description.pdf")
PY
```

**Last rendered result:** 4 pages, 46 KB (re-rendered 2026-05-28 after the compliance-sweep updates to §§1, 3, 5, 8 — table-cell rewrites kept the layout from spilling to a 5th page).

If you prefer pandoc + LaTeX (heavier toolchain, more typographic control), see the original recipe in this file's git history.

### 4. Produce the .docx for audit / red-line

Auditors typically prefer Word so they can **track changes** and leave comments. The submission ships a `.docx` rendered straight from the markdown source — not converted from the PDF — so the resulting structure (headings, tables, lists) is editable, not flattened to images.

```bash
# One-off install — bundles the pandoc binary so no system package needed
pip install --user pypandoc-binary

cd submission
python3 <<'PY'
import pypandoc
from pathlib import Path

pypandoc.convert_file(
    "HealthSync-Uganda-System-Description.md",
    "docx",
    format="gfm+pipe_tables+task_lists",
    outputfile="HealthSync-Uganda-System-Description.docx",
    extra_args=[
        "--standalone",
        "--toc", "--toc-depth=2",
        f"--resource-path={Path.cwd()}",
        "--metadata=title:HealthSync Uganda — System Description",
        "--metadata=subtitle:MoICT&NG Government Systems Prototype Showcase 2026",
        "--metadata=author:HealthSync Uganda team",
    ],
)
PY
```

**Last rendered result:** 20 KB; 6 tables (49 rows), Heading 1 + Heading 2 styles applied, 204 paragraphs. Opens in MS Word, LibreOffice Writer, and Google Docs without conversion warnings.

Why pandoc and not LibreOffice (PDF→DOCX)? LibreOffice's PDF importer flattens column boundaries, drops table styling, and converts inline code to image fragments — fine for read-only sharing, useless for line-by-line redlining. Pandoc reads the markdown source directly so tables stay tables and headings stay heading-styled.

## Pre-submission checklist

- [x] PDF page count ≤ 5 (current: **4 pages**, 46 KB, after compliance-sweep updates to §§1, 3, 5, 8)
- [x] DOCX rendered for audit / red-line (`HealthSync-Uganda-System-Description.docx`, 20 KB)
- [x] Diagrams 1–4 rendered and in `figures/` (last re-rendered 2026-05-26 22:57; structure unchanged in the compliance sweep so re-render not required)
- [ ] Figures 5 & 6 (UI screenshots) captured per §2
- [ ] Repository URL on the cover page resolves publicly
- [x] No `[Pilot lead to populate]` markers in the PDF body
- [ ] Contact details in `docs/TEAM.md §6` are populated with real names + reachable channels
- [x] Latest commit hash recorded for panel verification (see `Live deploys` block below)
- [x] Internal markdown link integrity verified (498/498 resolve)
- [x] Compliance-sweep changes (commits 5b386af..fa226a3) reflected in §§1, 3, 5, 8 of the system description

## Verification entry point for the panel

The panel can validate every claim in the submission against the live (open-source) repository starting at:

- `docs/SHOWCASE_EVALUATION_MAPPING.md` — criterion-to-evidence map with reviewer-runnable verification commands (`EV-CC-NN` IDs).
- `docs/README.md` §7 — role-based reading paths (Showcase reviewer; Security auditor; Code reviewer; SRE/on-call).
- Live deploys (Crane Cloud staging, currently at `sha-fa226a3`; verified clean against `tests/test_staging_regression.py` 44/44 on 2026-05-28):
  - Backend API: <https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io>
  - Frontend: <https://healthsync-frontend-staging-b73f2f98.renu-01.cranecloud.io>
  - FHIR R4 CapabilityStatement: <https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io/fhir/metadata>
  - OpenAPI 3.1 schema: <https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io/openapi.json>
  - Swagger UI: <https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io/docs>

## Showcase walkthrough — flagship demos panelists can run live

Each scenario takes ≤2 minutes from a phone or laptop browser. All accounts are documented in `CHANGELOG.md` under "Live (staging)".

### A. Citizen self-serve & data-protection transparency
1. Sign in at `/citizen/login` with NIN `CM85051712345X` / OTP `000000`.
2. Open **My records** → see encounter history across multiple facilities.
3. Open **Access history** → see who's read the record (the very act of opening it appears at the top — DPPA 2019 §14 made visible).
4. Open **Consent centre** → revoke a consent OR grant a new one (emergency-access scope).

### B. Healthcare worker — immunisation with duplicate-dose prevention
1. Sign in at `/login` with `nurse.gulu` / `demo1234`.
2. Click **Immunisations** → search by NIN `CF24091344332R` (the paediatric demo patient).
3. **Step 2** auto-renders the UNEPI-aware status table: which doses are complete, which are due now, which are overdue (highlighted amber, with day count).
4. **Step 3** dropdown flags blocked vaccines ("BCG — blocked: series already complete"). Override is possible only with a written clinical reason that's recorded in the audit log.
5. Administer a due vaccine → atomic write of an SNOMED-coded Observation + stock decrement.

### C. Family coordination — one parent, multiple children
1. Sign in at `/citizen/login` with `CF93081244778K` / `000000` (Wakiso mother).
2. Open **My family** → see two seeded children with per-child "overdue antigens" count.
3. Tap a child card → see that child's full immunisation schedule from the parent's account (caregiver-aware permission added in commit `8adb5eb`).

### D. Pharmacist supply-chain workflow
1. Sign in as `pharmacist.mbarara` / `demo1234`.
2. **Supply** → record an inbound batch (NMS supplier, lot, expiry).
3. **Dispense** → drains FEFO; the dispense is now audited per patient (DPPA §12 closure shipped 2026-05-26).
4. **Transfer history** (`/worker/supply/transfers`) → seeded with ~6 historical transfers across facilities.

### E. Mobile usability (a phone in a rural facility)
- Resize the browser window to 390×844 (iPhone 12) or open on a phone.
- The header collapses to a **hamburger** that reveals the role-filtered navigation in a slide-down sheet.
- Tables scroll horizontally on phones (forced `min-w-[640px]` wrapper); buttons meet the 44px Apple HIG tap-target minimum.

## Last verification run

Three layered test suites verify every claim in the system description, all run against the deployed Crane Cloud staging on 2026-05-28:

| Suite | Where | Count | Wall time | Result |
| --- | --- | --- | --- | --- |
| Backend unit + integration (in-memory SQLite) | `backend/tests/` | 33 | ~30 s | 33/33 (50 skipped — staging + Postgres-only gates) |
| Postgres-only integrity (append-only triggers, FKs, CHECK constraints, concurrent transfer locking) | `backend/tests/test_integrity_postgres.py` | 6 | <1 s | 6/6 against `postgres:16-alpine` + 3 extensions + alembic head |
| **Staging regression** — full feature surface against the live deploy | `backend/tests/test_staging_regression.py` (gated by `STAGING_URL`) | 44 | ~36 s | **44/44 against `sha-fa226a3`** |
| Frontend E2E (Playwright, staging) | `frontend/e2e/staging-smoke.spec.ts` | 19 | ~49 s | 19/19 |

The staging regression covers: 5 staff personas + citizen login; missing/malformed/invalid token → 401; `seed-admin` → 404; worker facility scope (nurse ≠ doctor); cross-facility patient GET → 403; citizen FHIR self-read 200 / other-patient 403; immunisation status (6 UNEPI antigens); encounter facility scope + eager-loaded observations; supply GROUP-BY + cross-facility 403; analytics district-scoped for `dho.gulu`; all 5 FHIR resources with `meta.lastUpdated`; Observation POST round-trip; idempotency replay + key-binding; audit-log purpose round-trip; pagination + invalid-input → 422; OpenAPI schema.

The staging regression's module-scoped readiness fixture requires **5 consecutive 200s on `/healthz`** before yielding the client, and the Crane Cloud deploy workflow now applies the same streak-based health check — these guard against the ingress-flicker window observed during pod rollover on 2026-05-28.

**Demo dataset:** 26 patients across 8 districts, 14 facilities, 14 supply items (6 vaccines), 4 caregiver links, populated audit log + transfer history.
