/**
 * Offline mutation queue backed by IndexedDB.
 *
 * Outgoing writes that fail because the device is offline are enqueued here
 * with their full request descriptor. A background drainer (see `drainer.ts`)
 * runs on `online` events and at app start, replaying them in FIFO order.
 *
 * Each entry carries an Idempotency-Key so the server safely deduplicates
 * replays after a network glitch.
 */

import { get, set, del, entries } from "idb-keyval";
import { ulid } from "@/lib/utils/ulid";

const QUEUE_PREFIX = "healthsync.queue.";

export type QueueEntry = {
  id: string;                       // ULID — ordering + uniqueness
  enqueuedAt: number;
  method: "POST" | "PATCH" | "PUT" | "DELETE";
  path: string;
  body: unknown;
  idempotencyKey: string;
  attempts: number;
  /** Why the user-facing UI should display this entry (for the sync drawer). */
  label: string;
};

export async function enqueue(entry: Omit<QueueEntry, "id" | "enqueuedAt" | "attempts">) {
  const full: QueueEntry = {
    ...entry,
    id: ulid(),
    enqueuedAt: Date.now(),
    attempts: 0,
  };
  await set(QUEUE_PREFIX + full.id, full);
  notify();
  return full;
}

export async function listPending(): Promise<QueueEntry[]> {
  const all = await entries<string, QueueEntry>();
  return all
    .filter(([k]) => k.startsWith(QUEUE_PREFIX))
    .map(([, v]) => v)
    .sort((a, b) => a.enqueuedAt - b.enqueuedAt);
}

/**
 * Items that the drainer marked as permanently failed (negative attempts —
 * server returned 4xx). The sync drawer should surface these for human
 * review rather than leaving them silently parked in IndexedDB.
 */
export async function listPermanentlyFailed(): Promise<QueueEntry[]> {
  const all = await listPending();
  return all.filter((e) => e.attempts < 0);
}

/** Items still eligible for automatic replay (non-negative attempts). */
export async function listReplayable(): Promise<QueueEntry[]> {
  const all = await listPending();
  return all.filter((e) => e.attempts >= 0);
}

export async function remove(id: string) {
  await del(QUEUE_PREFIX + id);
  notify();
}

export async function bumpAttempt(id: string, attempts: number) {
  const key = QUEUE_PREFIX + id;
  const cur = await get<QueueEntry>(key);
  if (!cur) return;
  await set(key, { ...cur, attempts });
  notify();
}

// ── Subscriber bus (lets React render a sync indicator) ───────────────────
const listeners = new Set<() => void>();
function notify() {
  listeners.forEach((l) => l());
}
export function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}
