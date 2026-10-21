import { createApi } from "@arba/api-client";
import { QueryClient, type Query } from "@tanstack/react-query";

export const api = createApi({
  client: "web",
  onSessionExpired: () => window.dispatchEvent(new Event("arba:session-expired")),
});

export const $api = api.$api;

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: true },
  },
});

/** Refetches project data after a change: one status change ripples through dependencies. */
export function invalidateProjects() {
  return queryClient.invalidateQueries({
    predicate: (query: Query) => String(query.queryKey[1]).startsWith("/api/v1/projects"),
  });
}
