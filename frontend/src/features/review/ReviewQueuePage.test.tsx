import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProposalSummary } from "../../api/types";
import { renderApp } from "../../test-utils";
import { fakeApi } from "./fakeApi";
import { json } from "./fixtures";
import { ReviewQueuePage } from "./ReviewQueuePage";

const OPEN = "GET /api/proposals?status=open";
const COMMITTED = "GET /api/proposals?status=committed";

function summary(over: Partial<ProposalSummary> = {}): ProposalSummary {
  return {
    id: 5,
    status: "open",
    summary: "Two facts about the Example Corp role",
    origin: "chat",
    created_at: "2026-10-01T09:30:00Z",
    applied_at: null,
    operation_count: 3,
    pending_count: 2,
    ...over,
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("ReviewQueuePage", () => {
  it("lists open proposals by default, each linking to its review", async () => {
    const api = fakeApi({ [OPEN]: [json([summary(), summary({ id: 6, summary: "One skill" })])] });
    renderApp(<ReviewQueuePage />, { route: "/review" });
    expect(screen.getByRole("heading", { level: 1, name: "Review queue" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Open" })).toHaveAttribute("aria-selected", "true");
    const link = await screen.findByRole("link", { name: /Two facts about the Example Corp role/ });
    expect(link).toHaveAttribute("href", "/review/5");
    expect(within(link).getByText("2 of 3 pending")).toBeInTheDocument();
    expect(link.querySelector("time")).toHaveAttribute("dateTime", "2026-10-01T09:30:00Z");
    expect(screen.getByRole("link", { name: /One skill/ })).toHaveAttribute("href", "/review/6");
    expect(api.calls(OPEN)).toHaveLength(1);
    expect(api.calls(COMMITTED)).toHaveLength(0);
  });

  it("switches to committed proposals on click", async () => {
    const api = fakeApi({
      [OPEN]: [json([])],
      [COMMITTED]: [
        json([
          summary({
            id: 4,
            status: "committed",
            summary: "Earlier facts",
            pending_count: 0,
            applied_at: "2026-09-30T08:00:00Z",
          }),
        ]),
      ],
    });
    renderApp(<ReviewQueuePage />, { route: "/review" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: "Committed" }));
    const link = await screen.findByRole("link", { name: /Earlier facts/ });
    expect(link).toHaveAttribute("href", "/review/4");
    expect(within(link).getByText("3 operations")).toBeInTheDocument();
    expect(api.calls(COMMITTED)).toHaveLength(1);
  });

  it("moves between tabs with the arrow keys", async () => {
    const api = fakeApi({ [OPEN]: [json([summary()])], [COMMITTED]: [json([])] });
    renderApp(<ReviewQueuePage />, { route: "/review" });
    await screen.findByRole("link", { name: /Two facts/ });
    const user = userEvent.setup();
    await user.tab();
    expect(screen.getByRole("tab", { name: "Open" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    const committed = screen.getByRole("tab", { name: "Committed" });
    expect(committed).toHaveFocus();
    expect(committed).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("No committed proposals yet.")).toBeInTheDocument();
    expect(api.calls(COMMITTED)).toHaveLength(1);
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("tab", { name: "Open" })).toHaveAttribute("aria-selected", "true");
  });

  it("says there is nothing to review and points to Chat", async () => {
    fakeApi({ [OPEN]: [json([])] });
    renderApp(<ReviewQueuePage />, { route: "/review" });
    const empty = await screen.findByText(
      (_, el) =>
        el?.tagName === "P" &&
        el.textContent === "Nothing to review. Tell the assistant something in Chat.",
    );
    expect(within(empty).getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/chat");
  });

  it("shows an error when the list cannot be loaded", async () => {
    fakeApi({ [OPEN]: [new TypeError("fetch failed")] });
    renderApp(<ReviewQueuePage />, { route: "/review" });
    expect(await screen.findByRole("alert")).toHaveTextContent("backend unreachable");
  });

  it("renders a hostile summary as inert text", async () => {
    const evil = "<img src=x onerror=alert(1)>";
    fakeApi({ [OPEN]: [json([summary({ summary: evil })])] });
    const { container } = renderApp(<ReviewQueuePage />, { route: "/review" });
    expect(await screen.findByText(evil)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });
});
