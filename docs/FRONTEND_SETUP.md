# Frontend setup

**Audience:** UI engineers, designers iterating on tokens, pilot partners running a local web client.
**Time to first render:** ~5 minutes on a clean workstation.

The `frontend/` package is a Next.js 16 application with TypeScript strict mode, Tailwind CSS, shadcn/ui primitives, TanStack Query v5 (with IndexedDB persistence), Zustand stores, a service-worker offline layer, and a lightweight i18n harness.

---

## 1. Prerequisites

| Tool      | Version  | Why                                                   |
| --------- | -------- | ----------------------------------------------------- |
| Bun       | **1.1+** | Package manager + runner (replaces npm / yarn / pnpm). `frontend/package.json` pins `engines.bun >= 1.1.0`. |
| Node      | not required | We do not use Node to run the dev server.        |
| The backend running on `http://localhost:8000` | — | The dev server reads from `NEXT_PUBLIC_API_BASE_URL`. |

Install Bun if you do not have it:

```bash
curl -fsSL https://bun.sh/install | bash
exec $SHELL                  # reload PATH
bun --version                # expect 1.1.x or newer
```

We deliberately do not use Node to run anything — Bun handles install, dev server, type-check, lint, and test. If your editor offers to use `npm install`, decline.

---

## 2. Install dependencies

```bash
cd frontend
bun install
```

This resolves and installs from `bun.lock`. Expect ~250 packages and a final size of ~280 MB under `node_modules/` (typical for a Next.js app — most of that is the swc + sharp + lightningcss native binaries).

---

## 3. Configure

The frontend has only two configurable values for local dev, both set via `frontend/.env.local` (optional — defaults work):

```bash
# frontend/.env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_APP_NAME=HealthSync Uganda
```

For Docker Compose runs these are overridden via the compose file — you do not need to edit anything.

---

## 4. Run the dev server

```bash
bun run dev                  # equivalent: next dev --turbo
```

Open <http://localhost:3000>. The landing page renders. The header carries the **language switcher** (English ↔ Luganda) and the **sync indicator**.

The dev server uses Turbopack for instant HMR. Initial cold start is ~3 seconds; subsequent edits propagate sub-300 ms.

### Sign in for the showcase walk-through

| Role                | Credentials                              | Lands on        |
| ------------------- | ---------------------------------------- | --------------- |
| Citizen             | NIN `CM85051712345X` · OTP `000000`       | `/citizen`      |
| Worker (nurse)      | `nurse.gulu` / `demo1234`                 | `/worker`       |
| Pharmacist          | `pharmacist.mbarara` / `demo1234`         | `/worker`       |
| District admin      | `district.kampala` / `demo1234`           | `/admin`        |
| Ministry admin      | `admin` / `admin1234`                     | `/admin`        |

(The seed must have run — see `make seed` in [BACKEND_SETUP.md](./BACKEND_SETUP.md).)

---

## 5. Type-check, lint, build

```bash
bun run typecheck            # tsc --noEmit (strict)
bun run lint                 # next lint (eslint + @next/eslint-plugin-next)
bun run build                # production build with PWA + service worker
bun run start                # serve the production build on :3000
```

The build emits a `frontend/.next` directory; `bun run start` serves it.

For the production preview the service worker is registered. Open DevTools → Application → Service Workers to confirm `sw.js` is `activated and running`.

---

## 6. Verify the offline path

The offline contract is part of the user-facing promise. To verify it works on your machine:

1. Sign in as `nurse.gulu`.
2. Open DevTools → Network → throttling → **Offline**.
3. Navigate to "Enrol patient", fill in the form, submit.
4. Expect a toast: *"Saved offline — will sync when network returns"* and the header sync indicator badge incremented.
5. Switch the network back on. Wait ~2 s. The badge drains to zero.
6. Refresh the patient list — the new record is there.
7. Re-submit the **exact same** form. The backend rejects the duplicate by idempotency key and returns the original record id (no double-write).

If any of those steps fail, see [RUNBOOK.md](./RUNBOOK.md) §"Sync stuck".

---

## 7. Common errors

| Symptom                                                                  | Cause                                                                  | Fix                                                                                  |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `Failed to fetch http://localhost:8000`                                  | Backend not running, or `NEXT_PUBLIC_API_BASE_URL` mismatched.         | `make backend`; verify the env value.                                                |
| 401 on every request after login                                         | Token expired (citizens 2 h, staff 8 h) or local time skewed.          | Re-login; check system clock.                                                        |
| `Hydration failed because the initial UI does not match what was rendered on the server` | Reading a locale or session synchronously during SSR.                  | The provider in `frontend/src/lib/i18n/provider.tsx` reads localStorage in a `useEffect`. Don't change that. |
| Service worker keeps serving stale assets                                | The `buster` value in `providers.tsx` hasn't been bumped.              | Bump `buster` to invalidate the IndexedDB query cache.                               |
| `bun install` fails on `sharp` / `@img/sharp-libvips-*` native binary    | Wrong libc target (musl vs glibc).                                     | `bun install --force` after deleting `node_modules`.                                 |
| Tailwind classes do not pick up the new colours                          | Stale Turbopack cache.                                                 | Stop the server, `rm -rf .next`, `bun run dev`.                                      |

---

## 8. Project layout (frontend)

```
frontend/
├── public/                       # static assets, service worker, manifest, icons
│   ├── manifest.webmanifest
│   └── sw.js                     # service worker (SWR + offline queue)
├── src/
│   ├── app/                      # Next.js App Router pages
│   │   ├── globals.css           # design tokens (HSL CSS variables)
│   │   ├── layout.tsx            # root layout, fonts, skip link
│   │   ├── page.tsx              # landing
│   │   ├── citizen/              # citizen portal
│   │   ├── worker/               # nurse / pharmacist
│   │   ├── admin/                # district + ministry
│   │   └── login/                # staff login
│   ├── components/
│   │   ├── layout/               # Header, Providers, LocaleSwitcher
│   │   ├── offline/              # SyncIndicator, queue UI
│   │   └── ui/                   # shadcn primitives (Button, Card, Table, StatusBadge, …)
│   ├── lib/
│   │   ├── api/                  # fetch helpers + react-query hooks
│   │   ├── i18n/                 # dictionary + provider
│   │   ├── offline/              # IndexedDB mutation queue
│   │   ├── store/                # Zustand stores (auth, UI)
│   │   └── utils/                # cn(), env helpers, ulid
│   └── types/                    # generated API types
├── tailwind.config.ts            # theme extension (see DESIGN_SYSTEM)
├── next.config.ts                # security headers, PWA wiring
├── tsconfig.json                 # strict mode
├── package.json                  # scripts: dev, build, start, lint, typecheck
└── bun.lock                      # locked dep tree
```

For the visual language see [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md). For the offline architecture see [ADR 0003](./adr/0003-offline-first-frontend.md).

---

## 9. Adding a new language

The harness is intentionally small. To add Runyankole as `nyn`:

1. Open `frontend/src/lib/i18n/dictionary.ts`.
2. Add `nyn` to `LOCALES` and a new key under `dictionaries` with every English key translated.
3. TypeScript fails the build until every key is present — no missing translations can ship.
4. `bun run typecheck` to confirm.
5. The header `LocaleSwitcher` picks up the new locale automatically.

No build configuration or framework upgrade is needed.

---

## 10. Next steps

- Read [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) before touching colour, spacing, or typography.
- Read [ADR 0003](./adr/0003-offline-first-frontend.md) before touching the mutation queue.
- Walk the showcase path in [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) to confirm your build behaves identically to the reference.
