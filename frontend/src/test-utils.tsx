import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";

/**
 * Render `ui` inside a fresh, non-retrying query client and an in-memory router
 * at `route` (a path, optionally with a `?query`), optionally carrying router `state`
 * (as a `<Link state>` would).
 */
export function renderApp(
  ui: ReactElement,
  opts: { route?: string; state?: unknown } = {},
): RenderResult {
  const [pathname = "/", search = ""] = (opts.route ?? "/").split(/(?=\?)/);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[{ pathname, search, state: opts.state }]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const enc = new TextEncoder();

/** A streaming `Response` whose body yields exactly the given byte chunks. */
export function streamOfBytes(chunks: Uint8Array[]): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(c) {
        chunks.forEach((b) => c.enqueue(b));
        c.close();
      },
    }),
  );
}

/** A streaming `Response` whose body yields the given strings as UTF-8 chunks. */
export function streamOf(chunks: string[]): Response {
  return streamOfBytes(chunks.map((s) => enc.encode(s)));
}
