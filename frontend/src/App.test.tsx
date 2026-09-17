import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function stubFetch(response: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response as Response));
}

describe("App", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the product name immediately", async () => {
    stubFetch({ ok: true, json: async () => ({ status: "ok", version: "0.1.0" }) });
    render(<App />);
    expect(await screen.findByRole("heading", { name: /cvforge/i })).toBeInTheDocument();
  });

  it("reports the backend version once health resolves", async () => {
    stubFetch({ ok: true, json: async () => ({ status: "ok", version: "0.1.0" }) });
    render(<App />);
    expect(await screen.findByText(/backend 0\.1\.0/i)).toBeInTheDocument();
  });

  it("reports a clear failure when the backend is unreachable", async () => {
    stubFetch({ ok: false, status: 503 });
    render(<App />);
    expect(await screen.findByText(/backend unreachable/i)).toBeInTheDocument();
  });
});
