/**
 * Tiny ULID generator — sortable, URL-safe, 26 chars.
 * Crypto-strong randomness when available; falls back to Math.random for SSR/test.
 */

const ENCODING = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

function randomBytes(n: number): Uint8Array {
  const arr = new Uint8Array(n);
  if (typeof globalThis.crypto !== "undefined" && globalThis.crypto.getRandomValues) {
    globalThis.crypto.getRandomValues(arr);
  } else {
    for (let i = 0; i < n; i++) arr[i] = Math.floor(Math.random() * 256);
  }
  return arr;
}

function encodeTime(now: number, len: number): string {
  let n = now;
  let out = "";
  for (let i = len - 1; i >= 0; i--) {
    const mod = n % 32;
    out = ENCODING[mod] + out;
    n = (n - mod) / 32;
  }
  return out;
}

function encodeRandom(len: number): string {
  const bytes = randomBytes(len);
  let out = "";
  for (let i = 0; i < len; i++) out += ENCODING[bytes[i]! % 32];
  return out;
}

export function ulid(): string {
  return encodeTime(Date.now(), 10) + encodeRandom(16);
}
