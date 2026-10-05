import { QueryClient } from "@tanstack/react-query";

/** The production query client: one retry, no refetch on window focus. */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
  });
}
