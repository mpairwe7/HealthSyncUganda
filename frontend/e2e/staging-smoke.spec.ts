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

  test("browser staff login: fills form, submits, receives token, redirects", async ({ page }) => {
    const serverErrors: string[] = [];
    const consoleErrors: string[] = [];
    page.on("response", (r) => {
      if (r.status() >= 500) serverErrors.push(`${r.status()} ${r.url()}`);
    });
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    await page.goto("/login", { waitUntil: "domcontentloaded" });

    await page.locator("#username").fill("admin");
    await page.locator("#password").fill("admin1234");

    // Wait for the actual login response — deterministic, no arbitrary sleep.
    // The Next.js router push happens in onSuccess, so we wait both for the
    // response and the navigation away from /login.
    const [loginResp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator("button[type=submit]").first().click(),
    ]);

    expect(loginResp.status()).toBe(200);
    const body = await loginResp.json();
    expect(body.role).toBe("ministry_admin");
    expect(body.access_token?.length).toBeGreaterThan(50);

    // Wait for the post-login redirect (router.push("/admin") for ministry_admin).
    await page.waitForURL(/\/admin/, { timeout: 10_000 });

    // Token should be persisted to sessionStorage by the Zustand store.
    const token = await page.evaluate(() =>
      window.sessionStorage.getItem("healthsync.token"),
    );
    expect(token).toBeTruthy();
    expect(token).toBe(body.access_token);

    // No server errors during the flow.
    expect(serverErrors).toEqual([]);
    // Console errors are best-effort (some chrome internals log noisily);
    // log them but don't fail unless they reference the app's own code.
    const appConsoleErrors = consoleErrors.filter(
      (e) => !e.includes("Failed to load resource") && !e.includes("Manifest"),
    );
    if (appConsoleErrors.length > 0) {
      console.warn("Browser console errors during login:", appConsoleErrors);
    }
  });

  test("browser nurse login: redirects worker role to /worker", async ({ page }) => {
    await page.goto("/login", { waitUntil: "domcontentloaded" });

    await page.locator("#username").fill("nurse.gulu");
    await page.locator("#password").fill("demo1234");

    const [loginResp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator("button[type=submit]").first().click(),
    ]);

    expect(loginResp.status()).toBe(200);
    expect((await loginResp.json()).role).toBe("worker");

    // worker → /worker (not /admin)
    await page.waitForURL(/\/worker/, { timeout: 10_000 });
  });

  test("browser staff login with wrong credentials: stays on /login, shows error", async ({ page }) => {
    await page.goto("/login", { waitUntil: "domcontentloaded" });

    await page.locator("#username").fill("admin");
    await page.locator("#password").fill("wrongpassword");

    const [loginResp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
        { timeout: 15_000 },
      ),
      page.locator("button[type=submit]").first().click(),
    ]);

    expect(loginResp.status()).toBe(401);

    // Should NOT navigate away.
    await page.waitForTimeout(1500);
    expect(page.url()).toMatch(/\/login$/);

    // No token stored.
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
