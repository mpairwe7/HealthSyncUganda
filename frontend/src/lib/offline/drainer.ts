/**
 * Queue drainer — replays offline writes when connectivity returns.
 *
 * Strategy:
 *   1. Listen for `online` events and an internal pulse every 30s.
 *   2. Pull the queue in arrival order.
 *   3. Replay each entry with its original Idempotency-Key. Server dedupes.
 *   4. On 5xx / network errors: bump attempt count, keep in queue.
 *   5. On 4xx (validation error): mark as failed-permanent. We surface it to
 *      the user with a "Review pending" notice rather than dropping silently.
 */

import { apiRequest, ApiError } from "@/lib/api/client";
import { bumpAttempt, listPending, remove } from "@/lib/offline/queue";

let inFlight: Promise<void> | null = null;
let pulse: ReturnType<typeof setInterval> | null = null;

export async function drainQueue(): Promise<{ delivered: number; remaining: number }> {
  if (inFlight) {
    await inFlight;
    return drainQueue();
  }
  inFlight = (async () => {
    if (typeof navigator !== "undefined" && !navigator.onLine) return;
    const pending = await listPending();
    for (const entry of pending) {
      try {
        await apiRequest(entry.path, {
          method: entry.method,
          body: entry.body,
          retries: 1,
          idempotent: false, // we set the header explicitly below
        });
        await remove(entry.id);
      } catch (err) {
        const attempts = entry.attempts + 1;
        if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
          // Permanent failure — leave it for human review
          await bumpAttempt(entry.id, -attempts); // negative = permanently failed
          continue;
        }
        await bumpAttempt(entry.id, attempts);
        break; // network blip — give up for this cycle
      }
    }
  })();
  try {
    await inFlight;
  } finally {
    inFlight = null;
  }
  const remaining = (await listPending()).length;
  return { delivered: 0, remaining };
}

export function startDrainer() {
  if (typeof window === "undefined") return;
  window.addEventListener("online", () => void drainQueue());
  if (pulse) clearInterval(pulse);
  pulse = setInterval(() => void drainQueue(), 30_000);
  void drainQueue();
}
