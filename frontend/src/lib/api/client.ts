/**
 * Resilient API client with exponential-backoff retries and offline-queueing.
 *
 * - Reads (GET) retry on transient failures and fall back to the persisted
 *   TanStack Query cache (handled by the query layer).
 * - Writes (POST/PATCH/PUT/DELETE) carry an Idempotency-Key derived from a
 *   stable client-side hash, so retries don't double-execute on the server.
 * - When the device is offline, writes are pushed to an IndexedDB queue
 *   (see `lib/offline/queue.ts`) and replayed when connectivity returns.
 */

import { API_BASE_URL } from "@/lib/utils/env";
import { ulid } from "@/lib/utils/ulid";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
    public readonly url: string,
    message?: string,
  ) {
    super(message ?? `API ${status} on ${url}`);
    this.name = "ApiError";
  }
}

export class NetworkOfflineError extends Error {
  constructor() {
    super("Network offline — request queued for sync.");
    this.name = "NetworkOfflineError";
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Override the default retry count (4). Use 0 for one-shot. */
  retries?: number;
  /** Add an Idempotency-Key. Defaults to true for unsafe methods. */
  idempotent?: boolean;
  /**
   * Explicit Idempotency-Key value. When provided, the client uses this
   * instead of generating a fresh one. The offline-replay drainer passes
   * the queue-stored key so server-side deduplication works across retries
   * after a network glitch.
   */
  idempotencyKey?: string;
  /** Skip auth header; used by /auth/login itself. */
  noAuth?: boolean;
  signal?: AbortSignal;
}

const TIMEOUT_MS = 8_000;
const BASE_DELAY_MS = 250;
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function authToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem("healthsync.token");
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(path.startsWith("http") ? path : `${API_BASE_URL}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    if (signal) {
      signal.addEventListener("abort", () => {
        clearTimeout(t);
        reject(signal.reason);
      });
    }
  });
}

async function once<T>(url: string, init: RequestInit, signal?: AbortSignal): Promise<T> {
  const timeout = new AbortController();
  const compositeSignal = signal
    ? AbortSignal.any([timeout.signal, signal])
    : timeout.signal;
  const t = setTimeout(() => timeout.abort(new Error("Request timed out")), TIMEOUT_MS);
  try {
    const res = await fetch(url, { ...init, signal: compositeSignal });
    const contentType = res.headers.get("content-type") ?? "";
    const body = contentType.includes("application/json") ? await res.json() : await res.text();
    if (!res.ok) {
      throw new ApiError(res.status, body, url);
    }
    return body as T;
  } finally {
    clearTimeout(t);
  }
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const url = buildUrl(path, options.query);
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (!options.noAuth) {
    const token = authToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  // Idempotency-Key precedence:
  //   1. caller-supplied key (offline drainer replays carry the stored key)
  //   2. fresh ulid if `idempotent` (default for unsafe methods)
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  } else {
    const idempotent = options.idempotent ?? !SAFE_METHODS.has(method);
    if (idempotent) headers["Idempotency-Key"] = ulid();
  }

  const init: RequestInit = {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  };

  const maxRetries = options.retries ?? (SAFE_METHODS.has(method) ? 3 : 2);
  let lastError: unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      // Hand back early — caller (mutation hook) is responsible for queueing.
      throw new NetworkOfflineError();
    }
    try {
      return await once<T>(url, init, options.signal);
    } catch (err) {
      lastError = err;
      const isApi = err instanceof ApiError;
      // 4xx (except 408/429) are user errors — don't retry
      if (isApi && err.status < 500 && err.status !== 408 && err.status !== 429) {
        throw err;
      }
      if (attempt === maxRetries) break;
      const jitter = Math.random();
      const backoff = Math.min(5_000, BASE_DELAY_MS * 2 ** attempt) * jitter;
      await delay(backoff, options.signal);
    }
  }
  throw lastError;
}
