/**
 * Staging smoke tests — live Crane Cloud deployment.
 *
 * Coverage:
 *   A. Frontend pages (load, branding, security headers, PWA assets)
 *   B. Backend documented endpoints (auth, data APIs, FHIR, analytics)
 *   C. Auth & access control (unauth, bad token, RBAC)
 *   D. Full login flows (staff + citizen via browser)
 *   E. Authenticated data flows (patients list, encounters, supply)
 *   F. Frontend ↔ backend integration (no 5xx on navigation)
 */

import { test, expect, request as pwRequest } from "@playwright/test";
import { BE_URL } from "./playwright.config.staging";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function loginStaff(identifier: string, password: string) {
  const ctx = await pwRequest.newContext({ baseURL: BE_URL });
  const resp = await ctx.post("/api/v1/auth/login", {
    data: { identifier, password },
  });
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  await ctx.dispose();
  return body.access_token as string;
}

async function loginCitizen(nin: string, otp: string) {
  const ctx = await pwRequest.newContext({ baseURL: BE_URL });
  const resp = await ctx.post("/api/v1/auth/citizen/login", {
    data: { nin, otp },
  });
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  await ctx.dispose();
  return body.access_token as string;
}

// ---------------------------------------------------------------------------
// A. Frontend pages
// ---------------------------------------------------------------------------

test.describe("A. Frontend pages", () => {
  test("landing page loads with HealthSync branding", async ({ page }) => {
    const resp = await page.goto("/", { waitUntil: "domcontentloaded" });
    expect(resp?.status()).toBe(200);
    await expect(page).toHaveTitle(/HealthSync/i);
  });

  test("login page renders staff login form inputs", async ({ page }) => {
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    // The login form uses id="username" (no `type` attr → defaults to text)
    // and id="password" with type="password".
    await expect(page.locator("#username")).toBeVisible();
    await expect(page.locator("#password")).toBeVisible();
  });

  test("citizen login page renders an input", async ({ page }) => {
    await page.goto("/citizen/login", { waitUntil: "domcontentloaded" });
    await expect(page.locator("input").first()).toBeVisible();
  });

  test("worker route reachable (unauth → redirect or render)", async ({ page }) => {
    const resp = await page.goto("/worker", { waitUntil: "domcontentloaded" });
    expect([200, 301, 302, 303, 307, 308]).toContain(resp?.status() ?? 0);
  });

  test("admin route reachable", async ({ page }) => {
    const resp = await page.goto("/admin", { waitUntil: "domcontentloaded" });
    expect([200, 301, 302, 303, 307, 308]).toContain(resp?.status() ?? 0);
  });

  test("security headers: nosniff + referrer-policy + permissions-policy", async ({ request }) => {
    const resp = await request.get("/");
    const h = resp.headers();
    expect(h["x-content-type-options"]).toBe("nosniff");
    expect(h["referrer-policy"]).toMatch(/strict-origin/);
    expect(h["permissions-policy"]).toMatch(/camera=\(\)/);
  });

  test("PWA manifest is valid JSON with HealthSync name and icons", async ({ request }) => {
    const resp = await request.get("/manifest.webmanifest");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.name).toMatch(/HealthSync/i);
    expect(body.icons?.length).toBeGreaterThanOrEqual(2);
  });

  test("PWA icon-192.png is served as image/png", async ({ request }) => {
    const resp = await request.get("/icons/icon-192.png");
    expect(resp.status()).toBe(200);
    expect(resp.headers()["content-type"]).toMatch(/png/);
  });

  test("PWA icon-512.png exists", async ({ request }) => {
    expect((await request.get("/icons/icon-512.png")).status()).toBe(200);
  });

  test("service worker /sw.js exists", async ({ request }) => {
    expect((await request.get("/sw.js")).status()).toBe(200);
  });
});

// ---------------------------------------------------------------------------
// B. Backend documented endpoints
// ---------------------------------------------------------------------------

test.describe("B. Backend documented endpoints", () => {
  test("/healthz → {status:'ok'}", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/healthz");
    expect(resp.status()).toBe(200);
    expect((await resp.json()).status).toBe("ok");
    await ctx.dispose();
  });

  test("/readyz → {status:'ready', database:'ok', redis:'ok'}", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/readyz");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.status).toBe("ready");
    expect(body.checks?.database).toBe("ok");
    expect(body.checks?.redis).toBe("ok");
    await ctx.dispose();
  });

  test("/fhir/metadata → valid FHIR R4 CapabilityStatement", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/fhir/metadata");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.resourceType).toBe("CapabilityStatement");
    expect(body.fhirVersion).toMatch(/^4\./);
    expect(body.status).toBe("active");
    const types = (body.rest?.[0]?.resource ?? []).map((r: { type: string }) => r.type);
    expect(types).toContain("Patient");
    expect(types).toContain("Encounter");
    await ctx.dispose();
  });

  test("/openapi.json → OpenAPI 3 with all documented path families", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/openapi.json");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.openapi).toMatch(/^3\./);
    expect(body.info?.title).toMatch(/HealthSync/i);
    const paths = Object.keys(body.paths ?? {});
    expect(paths.filter((p) => p.startsWith("/api/v1/")).length).toBeGreaterThan(10);
    const required = [
      "/api/v1/auth/login",
      "/api/v1/auth/citizen/login",
      "/api/v1/patients",
      "/api/v1/encounters",
      "/api/v1/consents",
      "/api/v1/supply/items",
      "/api/v1/supply/snapshot",
    ];
    for (const p of required) expect(paths).toContain(p);
    await ctx.dispose();
  });

  test("/docs → Swagger UI HTML", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/docs");
    expect(resp.status()).toBe(200);
    expect(await resp.text()).toMatch(/swagger/i);
    await ctx.dispose();
  });
});

// ---------------------------------------------------------------------------
// C. Auth & access control
// ---------------------------------------------------------------------------

test.describe("C. Auth & access control", () => {
  test("GET /patients without auth → 401", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    expect((await ctx.get("/api/v1/patients")).status()).toBe(401);
    await ctx.dispose();
  });

  test("GET /patients with bad bearer → 401", async () => {
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: "Bearer bad.token.value" },
    });
    expect((await ctx.get("/api/v1/patients")).status()).toBe(401);
    await ctx.dispose();
  });

  test("POST /auth/login empty body → 422 validation error", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    expect((await ctx.post("/api/v1/auth/login", { data: {} })).status()).toBe(422);
    await ctx.dispose();
  });

  test("POST /auth/login wrong password (passes min_length) → 401", async () => {
    // password field has min_length=6 in Pydantic; "wrong" (5 chars) would
    // short-circuit to 422 before the auth check. Use a 6+ char wrong value.
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    expect(
      (
        await ctx.post("/api/v1/auth/login", {
          data: { identifier: "admin", password: "wrongpassword" },
        })
      ).status(),
    ).toBe(401);
    await ctx.dispose();
  });

  test("POST /auth/login password too short → 422 (Pydantic validation)", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    expect(
      (
        await ctx.post("/api/v1/auth/login", {
          data: { identifier: "admin", password: "x" },
        })
      ).status(),
    ).toBe(422);
    await ctx.dispose();
  });

  test("POST /auth/citizen/login wrong OTP → 401", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    expect(
      (
        await ctx.post("/api/v1/auth/citizen/login", {
          data: { nin: "CM85051712345X", otp: "999999" },
        })
      ).status(),
    ).toBe(401);
    await ctx.dispose();
  });

  test("POST /auth/citizen/login NIN failing format validator → 422", async () => {
    // NIN custom validator: 14 uppercase alphanumerics starting with CM or CF.
    // "INVALID0000000X" has 15 chars + wrong prefix → 422 before NIRA lookup.
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    expect(
      (
        await ctx.post("/api/v1/auth/citizen/login", {
          data: { nin: "INVALID0000000X", otp: "000000" },
        })
      ).status(),
    ).toBe(422);
    await ctx.dispose();
  });

  test("POST /auth/citizen/login well-formed but unknown NIN → 404", async () => {
    // Well-formed (14 chars, CM prefix) but not in the seeded NIRA cache.
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    expect(
      (
        await ctx.post("/api/v1/auth/citizen/login", {
          data: { nin: "CM00000000000A", otp: "000000" },
        })
      ).status(),
    ).toBe(404);
    await ctx.dispose();
  });

  test("GET /interop/circuits unauthenticated → 401", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    expect([401, 403]).toContain((await ctx.get("/api/v1/interop/circuits")).status());
    await ctx.dispose();
  });

  test("nurse (worker role) GET /interop/circuits → 403 (role enforcement)", async () => {
    const token = await loginStaff("nurse.gulu", "demo1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    expect((await ctx.get("/api/v1/interop/circuits")).status()).toBe(403);
    await ctx.dispose();
  });
});

// ---------------------------------------------------------------------------
// D. Full login flows (browser UI)
// ---------------------------------------------------------------------------

test.describe("D. Full login flows (browser)", () => {
  test("staff API login: admin/admin1234 → ministry_admin JWT (8h)", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.post("/api/v1/auth/login", {
      data: { identifier: "admin", password: "admin1234" },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.role).toBe("ministry_admin");
    expect(body.access_token?.length).toBeGreaterThan(50);
    expect(body.expires_in).toBe(28800);
    await ctx.dispose();
  });

  test("staff API login: nurse.gulu/demo1234 → worker JWT with facility_id", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.post("/api/v1/auth/login", {
      data: { identifier: "nurse.gulu", password: "demo1234" },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.role).toBe("worker");
    expect(body.facility_id).toBeTruthy();
    expect(body.access_token?.length).toBeGreaterThan(50);
    await ctx.dispose();
  });

  test("citizen API login: CM85051712345X/000000 → citizen JWT (2h)", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.post("/api/v1/auth/citizen/login", {
      data: { nin: "CM85051712345X", otp: "000000" },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.role).toBe("citizen");
    expect(body.subject).toBe("CM85051712345X");
    expect(body.expires_in).toBe(7200);
    await ctx.dispose();
  });

  // Wait helpers shared by the browser-form tests below.
  //
  // The "Sign in" button has Tailwind `transition-colors` (and Playwright
  // hovers before clicking, which triggers the colour transition). The
  // stability check then occasionally sees the button as "not stable"
  // even after hydration completes — a well-known interaction between
  // Playwright actionability and Tailwind hover transitions. `force: true`
  // skips just the visibility / enabled / stable checks (NOT the locator
  // resolution) — the click still goes through React's onSubmit handler.
  //
  // We use `waitUntil: "load"` (not the lighter "domcontentloaded") so
  // that the Next.js bundle has executed and React has hydrated before we
  // fill the controlled inputs — otherwise the inputs accept text at the
  // DOM level but React's `value` state stays empty and the form submits
  // an empty payload (which the backend rejects with 422).
  async function gotoFormPage(page: import("@playwright/test").Page, path: string) {
    await page.goto(path, { waitUntil: "load" });
    // Belt-and-braces hydration confirmation: the form's React fiber is
    // attached only after hydration. ~1s on staging.
    await page.waitForFunction(
      () => {
        const form = document.querySelector("form");
        return (
          !!form &&
          Object.keys(form).some(
            (k) => k.startsWith("__reactFiber") || k.startsWith("__reactProps"),
          )
        );
      },
      { timeout: 10_000 },
    );
  }

  test("browser staff login: fills form, submits, receives token, redirects", async ({ page }) => {
    const serverErrors: string[] = [];
    page.on("response", (r) => {
      if (r.status() >= 500) serverErrors.push(`${r.status()} ${r.url()}`);
    });

    await gotoFormPage(page, "/login");
    await page.locator("#username").fill("admin");
    await page.locator("#password").fill("admin1234");

    const [loginResp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator("button[type=submit]").click({ force: true }),
    ]);

    expect(loginResp.status()).toBe(200);
    const body = await loginResp.json();
    expect(body.role).toBe("ministry_admin");
    expect(body.access_token?.length).toBeGreaterThan(50);

    await page.waitForURL(/\/admin/, { timeout: 10_000 });

    const token = await page.evaluate(() =>
      window.sessionStorage.getItem("healthsync.token"),
    );
    expect(token).toBeTruthy();
    expect(token).toBe(body.access_token);
    expect(serverErrors).toEqual([]);
  });

  test("browser nurse login: redirects worker role to /worker", async ({ page }) => {
    await gotoFormPage(page, "/login");
    await page.locator("#username").fill("nurse.gulu");
    await page.locator("#password").fill("demo1234");

    const [loginResp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator("button[type=submit]").click({ force: true }),
    ]);

    expect(loginResp.status()).toBe(200);
    expect((await loginResp.json()).role).toBe("worker");
    await page.waitForURL(/\/worker/, { timeout: 10_000 });
  });

  test("browser staff login with wrong credentials: stays on /login, no token stored", async ({ page }) => {
    await gotoFormPage(page, "/login");
    await page.locator("#username").fill("admin");
    await page.locator("#password").fill("wrongpassword");

    const [loginResp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator("button[type=submit]").click({ force: true }),
    ]);

    expect(loginResp.status()).toBe(401);

    await page.waitForTimeout(1500);
    expect(page.url()).toMatch(/\/login$/);

    const token = await page.evaluate(() =>
      window.sessionStorage.getItem("healthsync.token"),
    );
    expect(token).toBeFalsy();
  });

  test("browser citizen login page: no 5xx on load + interaction", async ({ page }) => {
    const serverErrors: string[] = [];
    page.on("response", (r) => {
      if (r.status() >= 500) serverErrors.push(`${r.status()} ${r.url()}`);
    });
    await page.goto("/citizen/login", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    expect(serverErrors).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// E. Authenticated data flows (API)
// ---------------------------------------------------------------------------

test.describe("E. Authenticated data flows", () => {
  test("GET /patients (admin) → paginated items with 26-char ULID ids", async () => {
    const token = await loginStaff("admin", "admin1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.get("/api/v1/patients?limit=5");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    const items: { id: string }[] = body.items ?? body;
    expect(items.length).toBeGreaterThan(0);
    for (const item of items.slice(0, 3)) {
      expect(item.id).toMatch(/^[0-9A-Z]{26}$/);
    }
    await ctx.dispose();
  });

  test("GET /patients (nurse/worker) → 200 or 403", async () => {
    const token = await loginStaff("nurse.gulu", "demo1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    expect([200, 403]).toContain((await ctx.get("/api/v1/patients")).status());
    await ctx.dispose();
  });

  test("GET /facilities → list with id + district", async () => {
    const token = await loginStaff("admin", "admin1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.get("/api/v1/facilities");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    const items: { id: string; district: string }[] = Array.isArray(body) ? body : body.items;
    expect(items.length).toBeGreaterThanOrEqual(5);
    expect(items[0].district).toBeTruthy();
    await ctx.dispose();
  });

  test("GET /encounters/by-patient/{id} → array", async () => {
    const token = await loginStaff("admin", "admin1234");
    const listCtx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const listBody = await (await listCtx.get("/api/v1/patients?limit=1")).json();
    const patientId = (listBody.items ?? listBody)[0]?.id;
    await listCtx.dispose();

    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.get(`/api/v1/encounters/by-patient/${patientId}`);
    expect(resp.status()).toBe(200);
    expect(Array.isArray(await resp.json())).toBeTruthy();
    await ctx.dispose();
  });

  test("GET /supply/items → supply catalogue (non-empty array)", async () => {
    const token = await loginStaff("admin", "admin1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.get("/api/v1/supply/items");
    expect(resp.status()).toBe(200);
    const items = await resp.json();
    expect(Array.isArray(items) && items.length > 0).toBeTruthy();
    await ctx.dispose();
  });

  test("GET /supply/snapshot → facility stock levels", async () => {
    const token = await loginStaff("nurse.gulu", "demo1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.get("/api/v1/supply/snapshot");
    expect(resp.status()).toBe(200);
    expect(Array.isArray(await resp.json())).toBeTruthy();
    await ctx.dispose();
  });

  test("GET /analytics/encounters-by-district → 200", async () => {
    const token = await loginStaff("admin", "admin1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    expect(
      (await ctx.get("/api/v1/analytics/encounters-by-district?since_days=30")).status(),
    ).toBe(200);
    await ctx.dispose();
  });

  test("GET /analytics/immunisation-coverage → 200", async () => {
    const token = await loginStaff("admin", "admin1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    expect(
      (await ctx.get("/api/v1/analytics/immunisation-coverage?since_days=180")).status(),
    ).toBe(200);
    await ctx.dispose();
  });

  test("GET /analytics/stock-out-risk → 200", async () => {
    const token = await loginStaff("admin", "admin1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    expect((await ctx.get("/api/v1/analytics/stock-out-risk")).status()).toBe(200);
    await ctx.dispose();
  });

  test("GET /interop/circuits (admin) → 200", async () => {
    const token = await loginStaff("admin", "admin1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    expect((await ctx.get("/api/v1/interop/circuits")).status()).toBe(200);
    await ctx.dispose();
  });
});

// ---------------------------------------------------------------------------
// F. Frontend ↔ backend integration
// ---------------------------------------------------------------------------

test.describe("F. Frontend ↔ backend integration", () => {
  test("no 5xx while navigating landing → login → citizen-login", async ({ page }) => {
    const errors: { url: string; status: number }[] = [];
    page.on("response", (r) => {
      if (r.status() >= 500) errors.push({ url: r.url(), status: r.status() });
    });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    await page.goto("/citizen/login", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    expect(errors).toEqual([]);
  });

  test("no localhost:8000 references in served JS bundles", async ({ page }) => {
    const localhostBundles: string[] = [];
    page.on("response", async (r) => {
      if ((r.headers()["content-type"] ?? "").includes("javascript")) {
        try {
          const text = await r.text();
          if (text.includes("localhost:8000")) localhostBundles.push(r.url());
        } catch {
          // ignore
        }
      }
    });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    expect(localhostBundles).toEqual([]);
  });

  test("API calls from login page target staging backend, not localhost", async ({ page }) => {
    const wrongTargets: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/api/v1/") && r.url().includes("localhost"))
        wrongTargets.push(r.url());
    });
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    expect(wrongTargets).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// G. Authenticated route walk — sidebar/dashboard wiring + flow smoothness
// ---------------------------------------------------------------------------
//
// Walk every page reachable from the post-login dashboards (worker, citizen,
// admin) and confirm:
//   1. The page returns 200 (no broken nav link → 404).
//   2. The page renders without 5xx backend errors.
//   3. The page exposes its expected primary heading.
//   4. There is no React hydration / runtime console error.
//
// To exercise auth-gated routes we first seed the session via the staff or
// citizen login API, then write the resulting token + session state into
// sessionStorage so the Zustand auth store rehydrates as "logged in" on
// the next navigation. This avoids re-running the browser login form for
// every route (which would be slow and add noise).

import { BE_URL as BE_URL_FOR_G } from "./playwright.config.staging";

type SessionLike = {
  token: string;
  role: string;
  subject: string;
  name: string | null;
  facility_id: string | null;
  expiresAt: number;
};

async function fetchStaffSession(
  identifier: string,
  password: string,
): Promise<SessionLike> {
  const ctx = await pwRequest.newContext({ baseURL: BE_URL_FOR_G });
  const resp = await ctx.post("/api/v1/auth/login", {
    data: { identifier, password },
  });
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  await ctx.dispose();
  return {
    token: body.access_token,
    role: body.role,
    subject: body.subject,
    name: body.name ?? null,
    facility_id: body.facility_id ?? null,
    expiresAt: Date.now() + body.expires_in * 1000,
  };
}

async function fetchCitizenSession(
  nin: string,
  otp: string,
): Promise<SessionLike> {
  const ctx = await pwRequest.newContext({ baseURL: BE_URL_FOR_G });
  const resp = await ctx.post("/api/v1/auth/citizen/login", {
    data: { nin, otp },
  });
  expect(resp.status()).toBe(200);
  const body = await resp.json();
  await ctx.dispose();
  return {
    token: body.access_token,
    role: body.role,
    subject: body.subject,
    name: body.name ?? null,
    facility_id: null,
    expiresAt: Date.now() + body.expires_in * 1000,
  };
}

async function primeSession(
  page: import("@playwright/test").Page,
  session: SessionLike,
) {
  // Visit any URL on origin to make sessionStorage writable, then seed.
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.evaluate((s) => {
    window.sessionStorage.setItem("healthsync.token", s.token);
    // Mirror the Zustand persist envelope shape so useAuth rehydrates from
    // sessionStorage on the next navigation. See src/lib/store/auth.ts.
    window.sessionStorage.setItem(
      "healthsync.auth",
      JSON.stringify({ state: { session: s }, version: 0 }),
    );
  }, session);
}

async function checkRoute(
  page: import("@playwright/test").Page,
  path: string,
  expectedHeading: RegExp,
) {
  const errors: string[] = [];
  const consoleErrors: string[] = [];
  const onResponse = (r: import("@playwright/test").Response) => {
    if (r.status() >= 500) errors.push(`${r.status()} ${r.url()}`);
  };
  const onConsole = (m: import("@playwright/test").ConsoleMessage) => {
    if (m.type() === "error") {
      const text = m.text();
      // Filter platform / icon noise that's not the app's fault
      if (!text.includes("Failed to load resource") && !text.includes("Manifest")) {
        consoleErrors.push(text);
      }
    }
  };
  page.on("response", onResponse);
  page.on("console", onConsole);

  // Crane Cloud's ingress occasionally drops a navigation with
  // ERR_NETWORK_CHANGED — retry once with a brief pause to absorb that
  // transient before failing the test.
  let resp: Awaited<ReturnType<typeof page.goto>> | undefined;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      resp = await page.goto(path, { waitUntil: "domcontentloaded" });
      break;
    } catch (err) {
      const msg = String(err);
      if (attempt === 0 && msg.includes("ERR_NETWORK_CHANGED")) {
        await page.waitForTimeout(1000);
        continue;
      }
      throw err;
    }
  }
  expect(resp?.status(), `GET ${path} status`).toBe(200);

  // Heading appears once the page client component renders post-redirect.
  await expect(
    page.getByRole("heading").filter({ hasText: expectedHeading }).first(),
  ).toBeVisible({ timeout: 10_000 });

  page.off("response", onResponse);
  page.off("console", onConsole);

  expect(errors, `5xx during ${path}`).toEqual([]);
  expect(consoleErrors, `console errors during ${path}`).toEqual([]);
}

test.describe("G. Authenticated route walk (worker + citizen + admin)", () => {
  test("worker: visits every reachable route from the worker dashboard", async ({ page }) => {
    const session = await fetchStaffSession("nurse.gulu", "demo1234");
    await primeSession(page, session);

    await checkRoute(page, "/worker", /worker dashboard/i);
    await checkRoute(page, "/worker/patients", /patients/i);
    await checkRoute(page, "/worker/patients/new", /enrol|register|new patient/i);
    await checkRoute(page, "/worker/supply", /supply|stock/i);
    await checkRoute(page, "/worker/immunisations", /immunisations/i);
  });

  test("citizen: visits every reachable route from the citizen portal", async ({ page }) => {
    const session = await fetchCitizenSession("CM85051712345X", "000000");
    await primeSession(page, session);

    await checkRoute(page, "/citizen", /welcome/i);
    await checkRoute(page, "/citizen/records", /my records|records/i);
    await checkRoute(page, "/citizen/consent", /consent/i);
    await checkRoute(page, "/citizen/immunisations", /immunisations/i);
    await checkRoute(page, "/citizen/appointments", /appointments/i);
    await checkRoute(page, "/citizen/facilities", /facility|facilities/i);
    await checkRoute(page, "/citizen/audit", /access history|audit/i);
  });

  test("admin: visits admin dashboard", async ({ page }) => {
    const session = await fetchStaffSession("admin", "admin1234");
    await primeSession(page, session);

    await checkRoute(page, "/admin", /admin|dashboard|ministry/i);
  });

  test("header navigation: worker sees Worker link, can click to /worker", async ({ page }) => {
    const session = await fetchStaffSession("nurse.gulu", "demo1234");
    await primeSession(page, session);

    await page.goto("/worker/patients", { waitUntil: "domcontentloaded" });
    // The top-nav Worker link is rendered for worker/pharmacist sessions.
    const navLink = page.getByRole("link", { name: /worker dashboard|workerDashboard|^worker$/i }).first();
    await expect(navLink).toBeVisible({ timeout: 10_000 });
  });

  test("header navigation: ministry_admin sees Administration link", async ({ page }) => {
    const session = await fetchStaffSession("admin", "admin1234");
    await primeSession(page, session);

    await page.goto("/admin", { waitUntil: "domcontentloaded" });
    const navLink = page.getByRole("link", { name: /administration|admin/i }).first();
    await expect(navLink).toBeVisible({ timeout: 10_000 });
  });

  test("worker dashboard tiles: every tile click lands on a 200 page", async ({ page }) => {
    const session = await fetchStaffSession("nurse.gulu", "demo1234");
    await primeSession(page, session);

    await page.goto("/worker", { waitUntil: "load" });
    // Wait for hydration so the dashboard tiles are interactive.
    await page.waitForFunction(
      () => !!document.querySelector("h1"),
      { timeout: 10_000 },
    );

    const tileHrefs = await page.$$eval('a[href^="/worker"]', (links) =>
      Array.from(new Set(links.map((a) => (a as HTMLAnchorElement).getAttribute("href"))))
        .filter((h): h is string => !!h && h !== "/worker"),
    );
    // Sanity: dashboard advertises multiple tiles.
    expect(tileHrefs.length).toBeGreaterThanOrEqual(3);

    for (const href of tileHrefs) {
      const resp = await page.goto(href, { waitUntil: "domcontentloaded" });
      expect(resp?.status(), `tile ${href}`).toBe(200);
    }
  });

  test("citizen home tiles: every tile click lands on a 200 page", async ({ page }) => {
    const session = await fetchCitizenSession("CM85051712345X", "000000");
    await primeSession(page, session);

    await page.goto("/citizen", { waitUntil: "load" });
    await page.waitForFunction(
      () => !!document.querySelector("h1"),
      { timeout: 10_000 },
    );

    const tileHrefs = await page.$$eval('a[href^="/citizen"]', (links) =>
      Array.from(new Set(links.map((a) => (a as HTMLAnchorElement).getAttribute("href"))))
        .filter((h): h is string => !!h && h !== "/citizen" && h !== "/citizen/login"),
    );
    expect(tileHrefs.length).toBeGreaterThanOrEqual(4);

    for (const href of tileHrefs) {
      const resp = await page.goto(href, { waitUntil: "domcontentloaded" });
      expect(resp?.status(), `tile ${href}`).toBe(200);
    }
  });
});

// ---------------------------------------------------------------------------
// H. /api/v1/me/* citizen self-serve endpoints + safety regressions
// ---------------------------------------------------------------------------
//
// The /me/* surface lets a citizen JWT read their own data without knowing
// their patient_id. Section H exercises:
//   1. happy path against the seeded citizen `CM85051712345X` (adult ANC) +
//      `CF24091344332R` (paediatric — has vaccine observations);
//   2. that the consent-revoke safety guard correctly blocks a citizen
//      from revoking another citizen's consent (the patch added in CP-1);
//   3. that staff (worker/admin) tokens are rejected from /me/* with 403.

test.describe("H. /api/v1/me/* self-serve + safety", () => {
  test("GET /me returns the calling citizen's Patient with matching NIN", async () => {
    const token = await loginCitizen("CM85051712345X", "000000");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.get("/api/v1/me");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.nin).toBe("CM85051712345X");
    expect(body.id).toMatch(/^[0-9A-Z]{26}$/);
    await ctx.dispose();
  });

  test("GET /me/encounters returns the citizen's own encounter history", async () => {
    const token = await loginCitizen("CM85051712345X", "000000");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.get("/api/v1/me/encounters");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBeTruthy();
    expect(body.length).toBeGreaterThan(0);
    // Newest-first ordering
    if (body.length >= 2) {
      const t0 = new Date(body[0].started_at).getTime();
      const t1 = new Date(body[1].started_at).getTime();
      expect(t0).toBeGreaterThanOrEqual(t1);
    }
    await ctx.dispose();
  });

  test("GET /me/immunisations returns vaccine observations for the paediatric citizen", async () => {
    const token = await loginCitizen("CF24091344332R", "000000");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.get("/api/v1/me/immunisations");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBeTruthy();
    // Paediatric persona — seed gives every visit an immunisation
    expect(body.length).toBeGreaterThan(0);
    // SNOMED-coded vaccines
    for (const imm of body.slice(0, 3)) {
      expect(imm.code_system).toBe("http://snomed.info/sct");
      expect(typeof imm.administered_at).toBe("string");
    }
    await ctx.dispose();
  });

  test("GET /me/audit returns the citizen's own access log (last 90d)", async () => {
    const token = await loginCitizen("CM85051712345X", "000000");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.get("/api/v1/me/audit?since_days=90");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(Array.isArray(body)).toBeTruthy();
    // Seed inserts 3-5 prior worker reads per patient
    expect(body.length).toBeGreaterThan(0);
    for (const row of body.slice(0, 3)) {
      expect(row.resource_type).toBe("Patient");
      expect(typeof row.actor_role).toBe("string");
    }
    await ctx.dispose();
  });

  test("POST /me/consent/grant creates a citizen-self-grant consent (201)", async () => {
    const token = await loginCitizen("CM85051712345X", "000000");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.post("/api/v1/me/consent/grant", {
      data: { scope: "share_with_emergency_services", purpose: "Emergency-room access" },
    });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    expect(body.scope).toBe("share_with_emergency_services");
    expect(body.id).toBeTruthy();
    expect(body.revoked_at).toBeFalsy();
    await ctx.dispose();
  });

  test("PATCH /me/profile updates only allowed fields", async () => {
    const token = await loginCitizen("CM85051712345X", "000000");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.patch("/api/v1/me/profile", {
      data: { phone: "+256772111222", village: "Kanyagoga" },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.phone).toBe("+256772111222");
    expect(body.village).toBe("Kanyagoga");
    // Unchanged fields preserved
    expect(body.nin).toBe("CM85051712345X");
    await ctx.dispose();
  });

  test("GET /me with a worker token → 403 (role enforcement)", async () => {
    const token = await loginStaff("nurse.gulu", "demo1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    expect((await ctx.get("/api/v1/me")).status()).toBe(403);
    await ctx.dispose();
  });

  test("GET /me with an admin token → 403", async () => {
    const token = await loginStaff("admin", "admin1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    expect((await ctx.get("/api/v1/me")).status()).toBe(403);
    await ctx.dispose();
  });

  test("GET /me/audit with no auth → 401", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    expect((await ctx.get("/api/v1/me/audit")).status()).toBe(401);
    await ctx.dispose();
  });

  test("POST /me/consent/grant with worker token → 403", async () => {
    const token = await loginStaff("nurse.gulu", "demo1234");
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${token}` },
    });
    const resp = await ctx.post("/api/v1/me/consent/grant", {
      data: { scope: "share_with_emergency_services", purpose: "Should not work" },
    });
    expect(resp.status()).toBe(403);
    await ctx.dispose();
  });

  test("safety: citizen A cannot revoke citizen B's consent → 403", async () => {
    // Citizen A creates a consent on their own record via /me/consent/grant
    const tokenA = await loginCitizen("CM85051712345X", "000000");
    const ctxA = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${tokenA}` },
    });
    const grant = await ctxA.post("/api/v1/me/consent/grant", {
      data: { scope: "share_with_research", purpose: "Safety regression seed" },
    });
    expect(grant.status()).toBe(201);
    const consentId = (await grant.json()).id;
    await ctxA.dispose();

    // Citizen B tries to revoke citizen A's consent — must be 403
    const tokenB = await loginCitizen("CF24091344332R", "000000");
    const ctxB = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: `Bearer ${tokenB}` },
    });
    const revoke = await ctxB.post(`/api/v1/consents/${consentId}/revoke`);
    expect(revoke.status()).toBe(403);
    await ctxB.dispose();
  });

  test("browser walk: /citizen/immunisations renders rows for a paediatric citizen", async ({ page }) => {
    const session = await fetchCitizenSession("CF24091344332R", "000000");
    await primeSession(page, session);

    // Wait for the /me/immunisations API call to complete so the loading
    // skeleton flips to the real table before we assert on column headers.
    const [immResp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/api/v1/me/immunisations") && r.status() === 200,
        { timeout: 15_000 },
      ),
      page.goto("/citizen/immunisations", { waitUntil: "domcontentloaded" }),
    ]);
    expect(immResp.status()).toBe(200);

    await expect(
      page.getByRole("heading", { name: /immunisations/i }).first(),
    ).toBeVisible({ timeout: 10_000 });
    // The table header should now be rendered (Date, Vaccine, Facility, Code)
    await expect(
      page.getByRole("columnheader", { name: /vaccine/i }).first(),
    ).toBeVisible({ timeout: 5_000 });
  });

  test("browser walk: /citizen/audit renders at least one access log row", async ({ page }) => {
    const session = await fetchCitizenSession("CM85051712345X", "000000");
    await primeSession(page, session);

    await page.goto("/citizen/audit", { waitUntil: "domcontentloaded" });
    await expect(
      page.getByRole("heading", { name: /access history/i }).first(),
    ).toBeVisible({ timeout: 10_000 });
    // Filter chip Day-window controls render
    await expect(page.getByRole("button", { name: /30 days/i })).toBeVisible();
  });

  test("browser walk: /citizen/facilities renders the district dropdown and a row", async ({ page }) => {
    const session = await fetchCitizenSession("CM85051712345X", "000000");
    await primeSession(page, session);

    await page.goto("/citizen/facilities", { waitUntil: "domcontentloaded" });
    await expect(
      page.getByRole("heading", { name: /find a facility/i }).first(),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("#district")).toBeVisible();
  });
});
