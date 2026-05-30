import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config targeting the LIVE Crane Cloud staging deployment.
 *
 * Run:  bun run e2e:staging
 *
 * Override URLs via environment if the deploy URLs change:
 *   FE_URL=https://...  BE_URL=https://...  bun run e2e:staging
 *
 * Last verified URLs (2026-05-26):
 *   Frontend: https://healthsync-frontend-staging-b73f2f98.renu-01.cranecloud.io
 *   Backend:  https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io
 */

const FE_URL =
  process.env.FE_URL ??
  "https://healthsync-frontend-staging-b73f2f98.renu-01.cranecloud.io";

const BE_URL =
  process.env.BE_URL ??
  "https://healthsync-backend-staging-9b4ecff1.renu-01.cranecloud.io";

export default defineConfig({
  testDir: ".",
  // Single workflow, no parallelism — staging is single-replica; we don't
  // want to swamp it from a test runner.
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "../e2e-results/staging", open: "never" }],
  ],
  use: {
    baseURL: FE_URL,
    extraHTTPHeaders: {
      // Identify ourselves so cranecloud / NITA-U telemetry can distinguish
      // synthetic traffic from real users.
      "User-Agent": "HealthSync-Playwright-E2E/1.0 (staging-smoke)",
    },
    ignoreHTTPSErrors: false,
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1280, height: 800 },
        // Container / CI shells need a triple workaround for Chromium:
        //   1. No sandbox (no user-namespace privileges) — same as mmdc.
        //   2. disable-dev-shm-usage — shm is small in containers.
        //   3. TMPDIR pointed at a local fs — the default /tmp can land on
        //      NFS, where Chromium's SingletonLock fails with EOPNOTSUPP.
        //      We can't pass --user-data-dir directly (Playwright rejects
        //      it in launch args; says to use launchPersistentContext);
        //      TMPDIR env var is the supported escape hatch.
        // Safe for synthetic E2E against a known-controlled staging URL;
        // do NOT use this profile to browse arbitrary sites.
        launchOptions: {
          chromiumSandbox: false,
          args: [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
          ],
          env: {
            ...process.env,
            TMPDIR: `${process.env.HOME}/.cache/playwright-tmp`,
          },
        },
      },
    },
  ],
  metadata: {
    fe_url: FE_URL,
    be_url: BE_URL,
  },
});

// Re-export so test files can import the backend URL alongside the frontend.
export { BE_URL, FE_URL };
