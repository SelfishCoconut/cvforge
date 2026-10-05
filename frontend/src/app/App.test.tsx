import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../test-utils";
import { App } from "./App";

function stubHealth(response: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response as Response));
}

function stubHealthy(): void {
  stubHealth({ ok: true, json: async () => ({ status: "ok", version: "0.1.0" }) });
}

describe("App shell", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("offers the four primary destinations as links", () => {
    stubHealthy();
    renderApp(<App />, { route: "/chat" });
    const nav = screen.getByRole("navigation", { name: "Primary" });
    const names = within(nav)
      .getAllByRole("link")
      .map((a) => a.textContent);
    expect(names).toEqual(["Chat", "Review", "Knowledge", "Settings"]);
  });

  it.each([
    ["/chat", "Chat"],
    ["/review", "Review"],
    ["/review/3", "Review"],
    ["/knowledge/7", "Knowledge"],
    ["/settings", "Settings"],
  ])("marks %s as the current page under %s", (route, active) => {
    stubHealthy();
    renderApp(<App />, { route });
    const nav = screen.getByRole("navigation", { name: "Primary" });
    for (const link of within(nav).getAllByRole("link")) {
      if (link.textContent === active) expect(link).toHaveAttribute("aria-current", "page");
      else expect(link).not.toHaveAttribute("aria-current");
    }
  });

  it("redirects / to the chat page", async () => {
    stubHealthy();
    renderApp(<App />, { route: "/" });
    expect(await screen.findByRole("heading", { level: 1, name: "Chat" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("aria-current", "page");
  });

  it.each([
    ["/chat", "Chat"],
    ["/review", "Review queue"],
    ["/review/3", "Review proposal"],
    ["/knowledge", "Knowledge"],
    ["/knowledge/abc", "Entity not found"],
    ["/settings", "Settings"],
  ])("routes %s to its page", (route, heading) => {
    stubHealthy();
    renderApp(<App />, { route });
    expect(screen.getByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
  });

  it("shows a not-found page with a way home for unknown routes", () => {
    stubHealthy();
    renderApp(<App />, { route: "/nowhere/at/all" });
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    const main = screen.getByRole("main");
    expect(within(main).getByRole("link", { name: /chat/i })).toHaveAttribute("href", "/chat");
  });

  it("reports the backend version in the footer once health resolves", async () => {
    stubHealthy();
    renderApp(<App />, { route: "/chat" });
    const footer = screen.getByRole("contentinfo");
    expect(await within(footer).findByText("backend 0.1.0")).toBeInTheDocument();
  });

  it("reports an unreachable backend in the footer", async () => {
    stubHealth({ ok: false, status: 503, json: async () => ({}) });
    renderApp(<App />, { route: "/chat" });
    const footer = screen.getByRole("contentinfo");
    expect(await within(footer).findByText("backend unreachable")).toBeInTheDocument();
  });

  it("says it is checking the backend while health is pending", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    renderApp(<App />, { route: "/chat" });
    expect(within(screen.getByRole("contentinfo")).getByText(/checking backend/i)).toBeInTheDocument();
  });

  it("makes 'Skip to content' the first focusable element, targeting main", async () => {
    stubHealthy();
    renderApp(<App />, { route: "/chat" });
    await userEvent.tab();
    const skip = screen.getByRole("link", { name: "Skip to content" });
    expect(skip).toHaveFocus();
    expect(skip).toHaveAttribute("href", "#main");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
  });
});
