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

Last rendered: 2026-05-26 via `weasyprint` (PDF) + `mmdc` (PNGs), per the recipe in §3.

## Build

### 1. Render the Mermaid diagrams to PNG

The project's rendering rig of record is **`@mermaid-js/mermaid-cli` (`mmdc`)** with a `--no-sandbox` Chromium configuration because most container/CI shells lack the sandboxing privileges Puppeteer expects by default.

```bash
# One-off install
bun install -g @mermaid-js/mermaid-cli   # or: npm install -g @mermaid-js/mermaid-cli

# Puppeteer config to bypass the sandbox requirement
cat > /tmp/puppeteer-cfg.json <<'EOF'
{ "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
           "--disable-gpu", "--single-process"] }
EOF

# Render each diagram
cd submission
for fig in 01-c4-context 02-c4-container 03-resilience-flow 04-security-boundaries; do
  mmdc -i diagrams/${fig}.mmd \
       -o figures/${fig}.png \
       --backgroundColor white --width 1920 --height 1080 \
       --theme default \
       --puppeteerConfigFile /tmp/puppeteer-cfg.json
done
```

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

**Last rendered result:** 4 pages, 41 KB.

If you prefer pandoc + LaTeX (heavier toolchain, more typographic control), see the original recipe in this file's git history.

## Pre-submission checklist

- [x] PDF page count ≤ 5 (current: **4 pages**)
- [x] Diagrams 1–4 rendered and in `figures/`
- [ ] Figures 5 & 6 (UI screenshots) captured per §2
- [ ] Repository URL on the cover page resolves publicly
- [x] No `[Pilot lead to populate]` markers in the PDF body
- [ ] Contact details in `docs/TEAM.md §6` are populated with real names + reachable channels
- [ ] Latest commit hash recorded in the cover letter for panel verification
- [x] Internal markdown link integrity verified (498/498 resolve)

## Verification entry point for the panel

The panel can validate every claim in the submission against the live (open-source) repository starting at:

- `docs/SHOWCASE_EVALUATION_MAPPING.md` — criterion-to-evidence map with reviewer-runnable verification commands (`EV-CC-NN` IDs).
- `docs/README.md` §7 — role-based reading paths (Showcase reviewer; Security auditor; Code reviewer; SRE/on-call).
- Live deploys (Crane Cloud staging):
  - Backend API: <https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io>
  - Frontend: <https://healthsync-frontend-staging-b73f2f98.renu-01.cranecloud.io>
  - FHIR R4 CapabilityStatement: <https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io/fhir/metadata>
  - OpenAPI 3.1 schema: <https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io/openapi.json>
  - Swagger UI: <https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io/docs>
