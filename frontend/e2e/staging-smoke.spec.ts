/**
 * Staging smoke tests — run against the LIVE Crane Cloud deployment.
 *
 * These cover the same surface that `docs/SHOWCASE_EVALUATION_MAPPING.md`
 * lists as panel-verifiable, plus a few hand-crafted user-journey probes
 * a panel reviewer might run from a browser.
 *
 * Scope intentionally narrow: this is a smoke suite, not a regression
 * harness. Goals:
 *   1. Confirm the page bundles load and the HTTP surface is correct.
 *   2. Confirm the backend's documented endpoints respond as the
 *      Showcase mapping promises.
 *   3. Confirm key UI elements are reachable (login forms, navigation).
 *   4. Confirm security headers are present at the edge.
 *
 * Out of scope:
 *   - Interactive flows that mutate state (no real PHI in staging; we
 *     don't want random rows accumulating).
 *   - Performance / load (use scripts/loadtest-*.sh for that).
 *   - Visual regression (no baseline screenshots yet).
 */

import { test, expect, request as pwRequest } from "@playwright/test";
import { BE_URL } from "./playwright.config.staging";

test.describe("Frontend — landing & navigation", () => {
  // Use domcontentloaded (not "load" or "networkidle"); the frontend's
  // TanStack Query polling + service-worker fetches keep the network
  // perpetually busy, so "networkidle" never fires. DOM content is the
  // right signal for "page rendered" in a PWA shell.
  test("landing page loads with HealthSync branding", async ({ page }) => {
    const resp = await page.goto("/", { waitUntil: "domcontentloaded" });
    expect(resp?.status()).toBe(200);
    await expect(page).toHaveTitle(/HealthSync/i);
  });

  test("login page renders the staff login form", async ({ page }) => {
    const resp = await page.goto("/login", { waitUntil: "domcontentloaded" });
    expect(resp?.status()).toBe(200);
    const body = await page.content();
    expect(body.toLowerCase()).toMatch(/login|sign in/);
  });

  test("citizen login page reachable", async ({ page }) => {
    const resp = await page.goto("/citizen/login", { waitUntil: "domcontentloaded" });
    expect(resp?.status()).toBe(200);
  });

  test("worker dashboard route reachable (unauth → redirects or empty state)", async ({ page }) => {
    const resp = await page.goto("/worker", { waitUntil: "domcontentloaded" });
    expect([200, 301, 302, 303, 307, 308]).toContain(resp?.status() ?? 0);
  });

  test("admin dashboard route reachable", async ({ page }) => {
    const resp = await page.goto("/admin", { waitUntil: "domcontentloaded" });
    expect([200, 301, 302, 303, 307, 308]).toContain(resp?.status() ?? 0);
  });
});

test.describe("Frontend — PWA + security posture", () => {
  test("service worker is served at /sw.js", async ({ request }) => {
    const resp = await request.get("/sw.js");
    expect(resp.status()).toBe(200);
  });

  test("PWA manifest is served at /manifest.webmanifest", async ({ request }) => {
    const resp = await request.get("/manifest.webmanifest");
    expect(resp.status()).toBe(200);
    const ct = resp.headers()["content-type"] ?? "";
    expect(ct).toMatch(/manifest\+json|application\/json|text/);
  });

  test("response headers include the security profile from SECURITY.md", async ({ request }) => {
    const resp = await request.get("/");
    expect(resp.status()).toBe(200);
    const h = resp.headers();
    // The three headers documented in next.config.ts + SECURITY.md
    expect(h["x-content-type-options"]).toBe("nosniff");
    expect(h["referrer-policy"]).toContain("strict-origin");
    expect(h["permissions-policy"]).toContain("camera=()");
  });
});

test.describe("Backend — documented endpoints", () => {
  test("/healthz returns 200 with {status:'ok'}", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/healthz");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.status).toBe("ok");
    await ctx.dispose();
  });

  test("/readyz returns 200 with database+redis subsystem checks", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/readyz");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    // Subsystem checks should both be "ok" given the fixed Redis FQDN
    expect(body.status).toBe("ready");
    expect(body.checks.database).toBe("ok");
    expect(body.checks.redis).toBe("ok");
    await ctx.dispose();
  });

  test("/fhir/metadata returns a valid FHIR R4 CapabilityStatement", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/fhir/metadata");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.resourceType).toBe("CapabilityStatement");
    expect(body.fhirVersion).toMatch(/^4\./);
    expect(body.status).toBe("active");
    const resources: { type: string }[] = body.rest?.[0]?.resource ?? [];
    expect(resources.length).toBeGreaterThanOrEqual(4);
    const types = resources.map(r => r.type);
    expect(types).toContain("Patient");
    expect(types).toContain("Encounter");
    expect(types).toContain("Observation");
    await ctx.dispose();
  });

  test("/openapi.json is a valid OpenAPI 3 schema with /api/v1/ paths", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/openapi.json");
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.openapi).toMatch(/^3\./);
    expect(body.info?.title).toMatch(/HealthSync/i);
    const paths: Record<string, unknown> = body.paths ?? {};
    const apiV1 = Object.keys(paths).filter(p => p.startsWith("/api/v1/"));
    expect(apiV1.length).toBeGreaterThan(10);
    // Confirm the documented endpoint families are present
    expect(Object.keys(paths)).toEqual(
      expect.arrayContaining([
        "/api/v1/auth/login",
        "/api/v1/auth/citizen/login",
        "/api/v1/patients",
        "/api/v1/encounters",
        "/api/v1/consents",
      ]),
    );
    await ctx.dispose();
  });

  test("/docs serves the Swagger UI", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/docs");
    expect(resp.status()).toBe(200);
    const body = await resp.text();
    expect(body).toMatch(/swagger/i);
    await ctx.dispose();
  });
});

test.describe("Backend — auth & access control", () => {
  test("GET /api/v1/patients without auth returns 401 (not 5xx)", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/api/v1/patients");
    expect(resp.status()).toBe(401);
    await ctx.dispose();
  });

  test("GET /api/v1/patients with invalid bearer returns 401", async () => {
    const ctx = await pwRequest.newContext({
      baseURL: BE_URL,
      extraHTTPHeaders: { Authorization: "Bearer obviously-invalid" },
    });
    const resp = await ctx.get("/api/v1/patients");
    expect(resp.status()).toBe(401);
    await ctx.dispose();
  });

  test("POST /api/v1/auth/login with empty body returns 422 (validation, not 5xx)", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.post("/api/v1/auth/login", { data: {} });
    expect(resp.status()).toBe(422);
    await ctx.dispose();
  });

  test("POST /api/v1/auth/citizen/login with wrong OTP returns 401", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.post("/api/v1/auth/citizen/login", {
      data: { nin: "CM85051712345X", otp: "999999" },
    });
    expect(resp.status()).toBe(401);
    await ctx.dispose();
  });

  test("ministry_admin endpoint /api/v1/interop/circuits rejects unauthenticated calls", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BE_URL });
    const resp = await ctx.get("/api/v1/interop/circuits");
    // 401 unauth OR 403 forbidden (after auth) — both are correct defenses;
    // unauthenticated test → 401.
    expect([401, 403]).toContain(resp.status());
    await ctx.dispose();
  });
});

test.describe("Backend — frontend integration", () => {
  test("no 5xx responses observed while navigating login flow", async ({ page }) => {
    const failingResponses: { url: string; status: number }[] = [];
    page.on("response", r => {
      if (r.status() >= 500) failingResponses.push({ url: r.url(), status: r.status() });
    });
    await page.goto("/citizen/login", { waitUntil: "domcontentloaded" });
    // Give the page 3s to fire any bootstrap fetches without waiting for
    // network-idle (which never settles due to TanStack Query polling).
    await page.waitForTimeout(3000);
    expect(failingResponses).toEqual([]);
  });
});
