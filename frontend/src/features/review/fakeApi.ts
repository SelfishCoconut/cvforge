import { vi } from "vitest";

type Reply = Response | (() => Response) | Error;

/**
 * A fetch stub routed by "METHOD path". Each route takes a list of replies,
 * consumed in order; the last one repeats. An `Error` reply rejects (network
 * failure). Unrouted requests answer 599 so a test fails loudly.
 */
export function fakeApi(routes: Record<string, Reply[]>) {
  const queues = new Map(Object.entries(routes).map(([k, v]) => [k, [...v]]));
  const fn = vi.fn((input: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${input}`;
    const queue = queues.get(key);
    const next = queue && (queue.length > 1 ? queue.shift() : queue[0]);
    if (next === undefined) return Promise.resolve(new Response(key, { status: 599 }));
    if (next instanceof Error) return Promise.reject(next);
    return Promise.resolve(typeof next === "function" ? next() : next.clone());
  });
  vi.stubGlobal("fetch", fn);
  const calls = (key: string) =>
    fn.mock.calls.filter(([url, init]) => `${init?.method ?? "GET"} ${url}` === key);
  const bodyOf = (key: string, n = 0): unknown => {
    const init = calls(key)[n]?.[1];
    return init?.body === undefined ? undefined : JSON.parse(init.body as string);
  };
  return { fn, calls, bodyOf };
}
