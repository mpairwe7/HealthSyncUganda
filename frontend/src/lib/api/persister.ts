/**
 * IndexedDB-backed persister so the TanStack Query cache survives reloads
 * and the user can navigate the app while offline.
 */

import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import { get, set, del } from "idb-keyval";

export const idbPersister = createAsyncStoragePersister({
  storage: {
    getItem: (key) => get<string>(key).then((v) => v ?? null),
    setItem: (key, value) => set(key, value),
    removeItem: (key) => del(key),
  },
  key: "healthsync.tanstack-query",
  throttleTime: 1_000,
});
