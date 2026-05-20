/**
 * HealthSync Uganda Service Worker.
 *
 * Strategy:
 *   - Pre-cache the app shell (HTML, CSS, JS chunks) on install.
 *   - Stale-while-revalidate for GET API responses (further fallback to cache
 *     when offline).
 *   - Network-only for POST/PATCH/PUT/DELETE — the app handles offline queueing
 *     in IndexedDB itself.
 */

const CACHE_VERSION = "v1";
const SHELL_CACHE = `healthsync-shell-${CACHE_VERSION}`;
const API_CACHE = `healthsync-api-${CACHE_VERSION}`;

const SHELL_URLS = ["/", "/citizen", "/worker", "/admin", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_URLS)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((k) => {
          if (![SHELL_CACHE, API_CACHE].includes(k)) return caches.delete(k);
          return undefined;
        }),
      ),
    ).then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  const isApi = url.pathname.startsWith("/api/") || url.pathname.startsWith("/fhir/");

  if (isApi) {
    event.respondWith(
      (async () => {
        try {
          const live = await fetch(req);
          const cache = await caches.open(API_CACHE);
          cache.put(req, live.clone());
          return live;
        } catch {
          const cached = await caches.match(req);
          if (cached) return cached;
          return new Response(JSON.stringify({ offline: true }), {
            status: 503,
            headers: { "content-type": "application/json" },
          });
        }
      })(),
    );
    return;
  }

  event.respondWith(
    (async () => {
      const cached = await caches.match(req);
      if (cached) return cached;
      try {
        const fresh = await fetch(req);
        const cache = await caches.open(SHELL_CACHE);
        cache.put(req, fresh.clone());
        return fresh;
      } catch {
        return caches.match("/") as Promise<Response>;
      }
    })(),
  );
});
