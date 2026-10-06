import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useNavigate } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Committed } from "../../api/types";
import { renderApp } from "../../test-utils";
import { fakeApi } from "./fakeApi";
import { json, makeEvidence, makeOp, makeProposal } from "./fixtures";
import { ReviewPage } from "./ReviewPage";

const GET = "GET /api/proposals/5";
const COMMIT = "POST /api/proposals/5/commit";
const review = (opId: number) => `POST /api/proposals/5/operations/${opId}/review`;
const EVIDENCE = { "GET /api/evidence/40": [json(makeEvidence())] };

const two = makeProposal({
  operations: [
    makeOp({ id: 12, seq: 2, payload: { name: "Second", evidence_id: 40 } }),
    makeOp({ id: 11, seq: 1, payload: { name: "First", evidence_id: 40 } }),
  ],
});
const committed: Committed = {
  commit_id: 9,
  applied_operation_ids: [11, 12],
  entity_ids: {},
  index_pending: [],
};

function renderPage(state?: unknown) {
  return renderApp(
    <Routes>
      <Route path="/review/:id" element={<ReviewPage />} />
      <Route path="/review" element={<p>Queue</p>} />
    </Routes>,
    { route: "/review/5", ...(state === undefined ? {} : { state }) },
  );
}

const cardNamed = (name: string) =>
  screen.getByRole("heading", { level: 2, name: new RegExp(name) }).closest("article") as HTMLElement;

afterEach(() => vi.unstubAllGlobals());

describe("ReviewPage", () => {
  it("loads the proposal and shows one card per operation in seq order", async () => {
    fakeApi({ [GET]: [json(two)], ...EVIDENCE });
    renderPage();
    expect(screen.getByText("Loading proposal…")).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { level: 1, name: two.summary }),
    ).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(headings).toEqual(["Create entity: First", "Create entity: Second"]);
    expect(screen.getByRole("link", { name: /All proposals/ })).toHaveAttribute("href", "/review");
    expect(screen.queryByText(/Similarity search was unavailable/)).toBeNull();
  });

  it("says the proposal was not found on 404", async () => {
    fakeApi({ [GET]: [json({ detail: "proposal 5 not found" }, 404)] });
    renderPage();
    expect(await screen.findByText("Proposal not found")).toBeInTheDocument();
  });

  it("says the backend is unreachable on a network failure", async () => {
    fakeApi({ [GET]: [new TypeError("fetch failed")] });
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent("backend unreachable");
  });

  it("accepts a pending operation and updates the card from the returned proposal", async () => {
    const after = makeProposal({
      operations: [makeOp({ status: "accepted" })],
    });
    const api = fakeApi({
      [GET]: [json(makeProposal())],
      [review(11)]: [json(after)],
      ...EVIDENCE,
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Accept" }));
    expect(await screen.findByText("Accepted")).toBeInTheDocument();
    expect(api.bodyOf(review(11))).toEqual({ decision: "accept" });
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
    expect(api.calls(GET)).toHaveLength(1);
  });

  it("sends an edit with the edited payload", async () => {
    const edited = { name: "Staff engineer", evidence_id: 40 };
    const after = makeProposal({
      operations: [makeOp({ status: "edited", edited_payload: edited })],
    });
    const api = fakeApi({ [GET]: [json(makeProposal())], [review(11)]: [json(after)], ...EVIDENCE });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const box = screen.getByLabelText("Payload (JSON)");
    await user.clear(box);
    await user.click(box);
    await user.paste(JSON.stringify(edited));
    await user.click(screen.getByRole("button", { name: "Save edit" }));
    expect(await screen.findByRole("button", { name: "Edit again" })).toBeInTheDocument();
    expect(api.bodyOf(review(11))).toEqual({ decision: "edit", edited_payload: edited });
    expect(screen.queryByRole("button", { name: /accept/i })).toBeNull();
  });

  it("locks every decision and Commit while a review is in flight", async () => {
    let answer!: (r: Response) => void;
    const after = makeProposal({
      operations: [
        makeOp({ id: 11, seq: 1, status: "accepted", payload: { name: "First", evidence_id: 40 } }),
        makeOp({ id: 12, seq: 2, payload: { name: "Second", evidence_id: 40 } }),
      ],
    });
    fakeApi({
      [GET]: [json(two)],
      [review(11)]: [() => new Promise<Response>((resolve) => (answer = resolve))],
      ...EVIDENCE,
    });
    renderPage();
    await screen.findByRole("heading", { level: 1, name: two.summary });
    const user = userEvent.setup();
    await user.click(within(cardNamed("First")).getByRole("button", { name: "Accept" }));
    for (const b of within(cardNamed("Second")).getAllByRole("button")) expect(b).toBeDisabled();
    expect(screen.getByRole("button", { name: "Commit" })).toBeDisabled();
    answer(json(after));
    await waitFor(() =>
      expect(within(cardNamed("Second")).getByRole("button", { name: "Accept" })).toBeEnabled(),
    );
  });

  it("shows a failed review's detail next to its card and leaves state unchanged", async () => {
    fakeApi({
      [GET]: [json(two)],
      [review(12)]: [json({ detail: "edited payload is invalid" }, 422)],
      ...EVIDENCE,
    });
    renderPage();
    await screen.findByRole("heading", { level: 1, name: two.summary });
    const user = userEvent.setup();
    await user.click(within(cardNamed("Second")).getByRole("button", { name: "Reject" }));
    expect(await within(cardNamed("Second")).findByRole("alert")).toHaveTextContent(
      "edited payload is invalid",
    );
    expect(within(cardNamed("First")).queryByRole("alert")).toBeNull();
    expect(within(cardNamed("Second")).getByText("Awaiting review")).toBeInTheDocument();
  });

  it("refetches the proposal after a 409 on review", async () => {
    const api = fakeApi({
      [GET]: [json(makeProposal()), json(makeProposal({ status: "committed", operations: [makeOp({ status: "applied" })] }))],
      [review(11)]: [json({ detail: "proposal 5 is already committed" }, 409)],
      ...EVIDENCE,
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Accept" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("proposal 5 is already committed");
    await waitFor(() => expect(api.calls(GET)).toHaveLength(2));
    expect(await screen.findByText("Applied")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Commit" })).toBeNull();
  });

  it("disables Commit while operations are pending, with a visible reason", async () => {
    fakeApi({ [GET]: [json(two)], ...EVIDENCE });
    renderPage();
    const commit = await screen.findByRole("button", { name: "Commit" });
    expect(commit).toBeDisabled();
    expect(screen.getByText("2 operations still pending")).toBeInTheDocument();
    expect(commit).toHaveAccessibleDescription("2 operations still pending");
  });

  it("commits, reports the applied count, and makes the cards read-only", async () => {
    const ready = makeProposal({ operations: [makeOp({ status: "accepted" })] });
    const done = makeProposal({
      status: "committed",
      applied_at: "2026-10-01T10:00:00Z",
      operations: [makeOp({ status: "applied" })],
    });
    const api = fakeApi({
      [GET]: [json(ready), json(done)],
      [COMMIT]: [json({ ...committed, applied_operation_ids: [11] })],
      ...EVIDENCE,
    });
    renderPage();
    const commit = await screen.findByRole("button", { name: "Commit" });
    expect(commit).toBeEnabled();
    const user = userEvent.setup();
    await user.click(commit);
    expect(await screen.findByRole("status")).toHaveTextContent("Committed: 1 operation applied.");
    expect(api.calls(COMMIT)).toHaveLength(1);
    await waitFor(() => expect(api.calls(GET)).toHaveLength(2));
    expect(within(screen.getByRole("article")).queryAllByRole("button")).toEqual([]);
    expect(screen.queryByText(/not yet searchable/)).toBeNull();
  });

  it("says how many entities still await similarity indexing", async () => {
    const ready = makeProposal({ operations: [makeOp({ status: "edited", edited_payload: { name: "X" } })] });
    fakeApi({
      [GET]: [json(ready)],
      [COMMIT]: [json({ ...committed, index_pending: [3, 4] })],
      ...EVIDENCE,
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Commit" }));
    expect(
      await screen.findByText(
        "2 entities are not yet searchable for similarity; they will be indexed later.",
      ),
    ).toBeInTheDocument();
  });

  it("shows a 409 on commit verbatim and refetches the proposal", async () => {
    const ready = makeProposal({ operations: [makeOp({ status: "accepted" })] });
    const stale = makeProposal({ operations: [makeOp({ status: "pending" })] });
    const api = fakeApi({
      [GET]: [json(ready), json(stale)],
      [COMMIT]: [json({ detail: "1 operation(s) still pending" }, 409)],
      ...EVIDENCE,
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Commit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/^1 operation\(s\) still pending$/);
    await waitFor(() => expect(api.calls(GET)).toHaveLength(2));
    await waitFor(() => expect(screen.getByRole("button", { name: "Commit" })).toBeDisabled());
  });

  it("keeps the server's reason visible when a 409 commit flips the proposal to committed", async () => {
    const ready = makeProposal({ operations: [makeOp({ status: "accepted" })] });
    const done = makeProposal({
      status: "committed",
      applied_at: "2026-10-01T10:00:00Z",
      operations: [makeOp({ status: "applied" })],
    });
    fakeApi({
      [GET]: [json(ready), json(done)],
      [COMMIT]: [json({ detail: "proposal 5 is already committed" }, 409)],
      ...EVIDENCE,
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Commit" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Commit" })).toBeNull());
    expect(screen.getByRole("alert")).toHaveTextContent(/^proposal 5 is already committed$/);
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
  });

  it("does not carry one proposal's commit state over to the next route id", async () => {
    const ready = makeProposal({ operations: [makeOp({ status: "accepted" })] });
    const six = makeProposal({
      id: 6,
      summary: "Another proposal",
      operations: [makeOp({ id: 21, status: "accepted" })],
    });
    fakeApi({
      [GET]: [json(ready)],
      [COMMIT]: [json(committed)],
      "GET /api/proposals/6": [json(six)],
      ...EVIDENCE,
    });
    let go: (to: string) => void = () => undefined;
    function Capture() {
      go = useNavigate();
      return null;
    }
    renderApp(
      <>
        <Capture />
        <Routes>
          <Route path="/review/:id" element={<ReviewPage />} />
        </Routes>
      </>,
      { route: "/review/5" },
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Commit" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Committed");
    act(() => go("/review/6"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Another proposal" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("button", { name: "Commit" })).toBeEnabled();
  });

  it("shows a non-409 commit failure without refetching", async () => {
    const ready = makeProposal({ operations: [makeOp({ status: "accepted" })] });
    const api = fakeApi({
      [GET]: [json(ready)],
      [COMMIT]: [json({ detail: "database is locked" }, 500)],
      ...EVIDENCE,
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Commit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("database is locked");
    expect(api.calls(GET)).toHaveLength(1);
  });

  it("warns when similarity search was unavailable for this proposal", async () => {
    fakeApi({ [GET]: [json(makeProposal())], ...EVIDENCE });
    renderPage({ similarityAvailable: false });
    expect(
      await screen.findByText(
        "Similarity search was unavailable when this proposal was made; duplicates were not checked.",
      ),
    ).toBeInTheDocument();
  });

  it("opens a committed proposal read-only with no Commit button", async () => {
    fakeApi({
      [GET]: [
        json(
          makeProposal({
            status: "committed",
            applied_at: "2026-10-01T10:00:00Z",
            operations: [makeOp({ status: "applied" }), makeOp({ id: 12, seq: 2, status: "rejected" })],
          }),
        ),
      ],
      ...EVIDENCE,
    });
    renderPage();
    await screen.findByRole("heading", { level: 1, name: two.summary });
    expect(screen.queryAllByRole("button")).toEqual([]);
    expect(screen.getByText(/Committed/)).toBeInTheDocument();
  });

  it("treats a non-numeric id as not found without fetching", async () => {
    const api = fakeApi({});
    renderApp(
      <Routes>
        <Route path="/review/:id" element={<ReviewPage />} />
      </Routes>,
      { route: "/review/abc" },
    );
    expect(await screen.findByText("Proposal not found")).toBeInTheDocument();
    expect(api.fn).not.toHaveBeenCalled();
  });
});
