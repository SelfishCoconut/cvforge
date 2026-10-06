import { describe, expect, it } from "vitest";
import { makeQueryClient } from "./providers";

describe("makeQueryClient", () => {
  it("retries once and does not refetch on window focus", () => {
    const queries = makeQueryClient().getDefaultOptions().queries;
    expect(queries?.retry).toBe(1);
    expect(queries?.refetchOnWindowFocus).toBe(false);
  });

  it("returns a fresh client each call", () => {
    expect(makeQueryClient()).not.toBe(makeQueryClient());
  });
});
