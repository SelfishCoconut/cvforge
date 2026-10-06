import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./client";

function stub(response: Response | Error): ReturnType<typeof vi.fn> {
  const fn = vi.fn();
  if (response instanceof Error) fn.mockRejectedValue(response);
  else fn.mockImplementation(() => Promise.resolve(response.clone()));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api errors", () => {
  it("maps a string detail to ApiError", async () => {
    stub(json({ detail: "x" }, 404));
    const err = await api.getProposal(1).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).message).toBe("x");
  });

  it("joins validation-array msgs", async () => {
    stub(json({ detail: [{ msg: "a" }, { msg: "b" }] }, 422));
    await expect(api.getProposal(1)).rejects.toThrow("a; b");
  });

  it("falls back to HTTP status for a non-JSON body", async () => {
    stub(new Response("<html>", { status: 502 }));
    await expect(api.getProposal(1)).rejects.toThrow("HTTP 502");
  });

  it("falls back to HTTP status for an unrecognised JSON body", async () => {
    stub(json({ other: 1 }, 500));
    await expect(api.getProposal(1)).rejects.toThrow("HTTP 500");
  });

  it("maps a network failure to ApiError(0)", async () => {
    stub(new TypeError("fail"));
    const err = await api.health().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(0);
    expect((err as ApiError).message).toBe("backend unreachable");
  });
});

describe("api requests", () => {
  it("health returns the body", async () => {
    const fn = stub(json({ status: "ok", version: "1" }));
    expect(await api.health()).toEqual({ status: "ok", version: "1" });
    expect(fn.mock.calls[0]?.[0]).toBe("/api/health");
  });

  it("listEntities omits undefined params", async () => {
    const fn = stub(json([]));
    await api.listEntities({ kind: "skill" });
    expect(fn.mock.calls[0]?.[0]).toBe("/api/entities?kind=skill");
    await api.listEntities();
    expect(fn.mock.calls[1]?.[0]).toBe("/api/entities");
    await api.listEntities({ kind: "skill", state: "gap" });
    expect(fn.mock.calls[2]?.[0]).toBe("/api/entities?kind=skill&state=gap");
  });

  it("listProposals passes the status filter", async () => {
    const fn = stub(json([]));
    await api.listProposals("open");
    expect(fn.mock.calls[0]?.[0]).toBe("/api/proposals?status=open");
    await api.listProposals();
    expect(fn.mock.calls[1]?.[0]).toBe("/api/proposals");
  });

  it("reviewOperation posts decision and edited_payload", async () => {
    const fn = stub(json({ id: 1 }));
    await api.reviewOperation(3, 7, "edit", { name: "x" });
    const [url, init] = fn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/proposals/3/operations/7/review");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      decision: "edit",
      edited_payload: { name: "x" },
    });
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
  });

  it("commitProposal posts to the commit URL", async () => {
    const fn = stub(json({}));
    await api.commitProposal(3);
    const [url, init] = fn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/proposals/3/commit");
    expect(init.method).toBe("POST");
  });

  it("simple getters hit the right URLs", async () => {
    const fn = stub(json({}));
    await api.getEvidence(4);
    await api.getEntity(5);
    await api.getEdges(5);
    await api.getProvenance("edge", 6);
    await api.getSettings();
    expect(fn.mock.calls.map((c) => c[0])).toEqual([
      "/api/evidence/4",
      "/api/entities/5",
      "/api/entities/5/edges",
      "/api/provenance/edge/6",
      "/api/settings",
    ]);
  });

  it("putSettings sends PUT with the body", async () => {
    const fn = stub(json({}));
    await api.putSettings({ provider: "ollama" } as never);
    const [url, init] = fn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/settings");
    expect(init.method).toBe("PUT");
  });

  it("streamChat posts and returns the raw Response", async () => {
    const res = new Response("", { status: 200 });
    const fn = stub(res);
    const signal = new AbortController().signal;
    const got = await api.streamChat("hi", null, signal);
    expect(got.status).toBe(200);
    const [url, init] = fn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/chat/messages/stream");
    expect(JSON.parse(init.body as string)).toEqual({ text: "hi", conversation_id: null });
    expect(new Headers(init.headers).get("Accept")).toBe("application/x-ndjson");
    expect(init.signal).toBe(signal);
  });

  it("streamChat throws ApiError when not ok", async () => {
    stub(json({ detail: "nope" }, 400));
    await expect(api.streamChat("hi", 2)).rejects.toThrow("nope");
  });

  it("streamChat maps a network failure", async () => {
    stub(new TypeError("fail"));
    await expect(api.streamChat("hi", 2)).rejects.toThrow("backend unreachable");
  });
});
