import { QueryClient } from "@tanstack/react-query";

/**
 * QueryClient tuned for variable bandwidth:
 * - `staleTime: 60s` reduces refetch chatter on dashboards
 * - `gcTime: 7 days` keeps the persisted cache useful across sessions
 * - `retry: 3` with bounded backoff
 * - mutations stay live in the cache so the offline drainer can find them
 */
export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 60_000,
        gcTime: 7 * 24 * 60 * 60 * 1_000,
        refetchOnWindowFocus: false,
        refetchOnReconnect: "always",
        retry: 3,
        retryDelay: (i) => Math.min(5_000, 250 * 2 ** i) * Math.random(),
        networkMode: "offlineFirst",
      },
      mutations: {
        retry: 0,
        networkMode: "offlineFirst",
      },
    },
  });
}
