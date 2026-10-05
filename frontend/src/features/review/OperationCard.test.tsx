import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { OperationRecord } from "../../api/types";
import { renderApp } from "../../test-utils";
import { explain } from "./explain";
import { json, makeEvidence, makeOp } from "./fixtures";
import { OperationCard } from "./OperationCard";

type OnDecide = (
  decision: "accept" | "edit" | "reject",
  edited?: Record<string, unknown>,
) => Promise<string | null>;

function stubEvidence(response: () => Promise<Response>) {
  const fn = vi.fn<(input: string) => Promise<Response>>(response);
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderCard(
  op: OperationRecord,
  opts: { open?: boolean; onDecide?: OnDecide; error?: string | null } = {},
) {
  const onDecide = vi.fn<OnDecide>(opts.onDecide ?? (() => Promise.resolve(null)));
  const view = renderApp(
    <OperationCard
      op={op}
      proposalOpen={opts.open ?? true}
      busy={false}
      error={opts.error ?? null}
      onDecide={onDecide}
    />,
  );
  return { onDecide, ...view };
}

afterEach(() => vi.unstubAllGlobals());

describe("OperationCard", () => {
  it("shows the badge, the explanation, the op type and the fetched evidence excerpt", async () => {
    const fetch = stubEvidence(() => Promise.resolve(json(makeEvidence())));
    renderCard(makeOp({ classification: "duplicate" }));
    expect(screen.getByText("duplicate")).toBeInTheDocument();
    expect(screen.getByText(explain("duplicate", "create_entity"))).toBeInTheDocument();
    expect(screen.getByText("create_entity")).toBeInTheDocument();
    expect(screen.getByText("Loading evidence…")).toBeInTheDocument();
    expect(
      await screen.findByText("I worked as a backend engineer at Example Corp."),
    ).toBeInTheDocument();
    expect(screen.getByText("Chat message · message:1")).toBeInTheDocument();
    expect(fetch.mock.calls[0]?.[0]).toBe("/api/evidence/40");
  });

  it("says the evidence is unavailable when its fetch fails, without crashing", async () => {
    stubEvidence(() => Promise.resolve(json({ detail: "gone" }, 404)));
    renderCard(makeOp());
    expect(await screen.findByText("Evidence unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument();
  });

  it("says no evidence is cited when the payload has no evidence_id", () => {
    const fetch = stubEvidence(() => Promise.resolve(json(makeEvidence())));
    renderCard(makeOp({ payload: { op_type: "create_entity", name: "X" } }));
    expect(screen.getByText("No evidence cited")).toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("never offers accept on an edited operation (audit F7)", () => {
    stubEvidence(() => Promise.resolve(json(makeEvidence())));
    renderCard(
      makeOp({
        status: "edited",
        edited_payload: { op_type: "create_entity", name: "Senior backend engineer", evidence_id: 40 },
      }),
    );
    expect(screen.getByRole("button", { name: "Edit again" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /accept/i })).toBeNull();
  });

  it("offers accept, edit and reject on a pending operation and reports the decision", async () => {
    stubEvidence(() => Promise.resolve(json(makeEvidence())));
    const { onDecide } = renderCard(makeOp());
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Accept" }));
    expect(onDecide).toHaveBeenLastCalledWith("accept");
    await user.click(screen.getByRole("button", { name: "Reject" }));
    expect(onDecide).toHaveBeenLastCalledWith("reject");
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  it.each([
    ["accepted", ["Edit", "Reject"]],
    ["rejected", ["Accept", "Edit"]],
    ["applied", []],
  ])("a %s operation offers exactly %j", (status, names) => {
    stubEvidence(() => Promise.resolve(json(makeEvidence())));
    renderCard(makeOp({ status }));
    const article = screen.getByRole("article");
    expect(within(article).queryAllByRole("button").map((b) => b.textContent)).toEqual(names);
  });

  it("is read-only once the proposal is committed", () => {
    stubEvidence(() => Promise.resolve(json(makeEvidence())));
    renderCard(makeOp({ status: "accepted" }), { open: false });
    expect(within(screen.getByRole("article")).queryAllByRole("button")).toEqual([]);
  });

  it("shows the edited payload labelled as edited, as well as the original", () => {
    stubEvidence(() => Promise.resolve(json(makeEvidence())));
    renderCard(
      makeOp({
        status: "edited",
        edited_payload: { op_type: "create_entity", name: "Senior backend engineer", evidence_id: 40 },
      }),
    );
    expect(screen.getByRole("heading", { name: /Senior backend engineer/ })).toBeInTheDocument();
    const edited = screen.getByText("Edited payload").closest("details");
    expect(edited).not.toBeNull();
    expect(edited?.querySelector("pre")?.textContent).toContain('"Senior backend engineer"');
    const original = screen.getByText("Original payload").closest("details");
    expect(original?.querySelector("pre")?.textContent).toContain('"Backend engineer"');
  });

  it("summarises the payload in a heading and shows it as formatted JSON in a details block", () => {
    stubEvidence(() => Promise.resolve(json(makeEvidence())));
    renderCard(makeOp());
    expect(
      screen.getByRole("heading", { name: "Create entity: Backend engineer" }),
    ).toBeInTheDocument();
    const pre = screen.getByText("Payload").closest("details")?.querySelector("pre");
    expect(pre?.textContent).toBe(JSON.stringify(makeOp().payload, null, 2));
  });

  it("reaches the decision buttons in order by Tab and activates them with Enter and Space", async () => {
    stubEvidence(() => Promise.resolve(json(makeEvidence())));
    const { onDecide } = renderCard(makeOp());
    const user = userEvent.setup();
    const names: string[] = [];
    for (let i = 0; i < 10 && names.length < 3; i += 1) {
      await user.tab();
      const el = document.activeElement;
      if (el instanceof HTMLButtonElement) names.push(el.textContent ?? "");
    }
    expect(names).toEqual(["Accept", "Edit", "Reject"]);
    const heading = screen.getByRole("heading", { level: 2 });
    for (const name of names) {
      expect(screen.getByRole("button", { name })).toHaveAttribute("aria-describedby", heading.id);
    }
    screen.getByRole("button", { name: "Accept" }).focus();
    await user.keyboard("{Enter}");
    expect(onDecide).toHaveBeenLastCalledWith("accept");
    screen.getByRole("button", { name: "Reject" }).focus();
    await user.keyboard(" ");
    expect(onDecide).toHaveBeenLastCalledWith("reject");
  });

  it("shows a review error next to the card", () => {
    stubEvidence(() => Promise.resolve(json(makeEvidence())));
    renderCard(makeOp(), { error: "operation 11 is not pending" });
    expect(screen.getByRole("alert")).toHaveTextContent("operation 11 is not pending");
  });

  it("renders hostile excerpt and payload text inert and wraps a long unbroken string", async () => {
    const evil = "<img src=x onerror=alert(1)>";
    const long = "a".repeat(5000);
    stubEvidence(() => Promise.resolve(json(makeEvidence({ excerpt: `${evil} ${long}` }))));
    const { container } = renderCard(
      makeOp({
        classification: "<b>x</b>",
        payload: { name: `${evil}${long}`, evidence_id: 40, url: "javascript:alert(1)" },
        rationale: evil,
      }),
      { error: evil },
    );
    const excerpt = await screen.findByText(`${evil} ${long}`);
    expect(excerpt.className).toContain("break-words");
    const heading = screen.getByRole("heading", { level: 2 });
    expect(heading.className).toContain("break-words");
    expect(container.querySelector("pre")?.className).toContain("break-words");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    await waitFor(() => expect(screen.getByText("<b>x</b>")).toBeInTheDocument());
  });
});
