import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes, useNavigate } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../../test-utils";
import { makeEdge, makeEntity, makeProvenance } from "../../test/knowledge";
import { fakeApi } from "../review/fakeApi";
import { json } from "../review/fixtures";
import { EntityPage } from "./EntityPage";

const ENTITY = "GET /api/entities/3";
const EDGES = "GET /api/entities/3/edges";

afterEach(() => vi.unstubAllGlobals());

function renderAt(route: string) {
  return renderApp(
    <Routes>
      <Route path="/knowledge/:id" element={<EntityPage />} />
      <Route path="/knowledge" element={<p>list page</p>} />
    </Routes>,
    { route },
  );
}

describe("EntityPage", () => {
  it("shows the entity with its attributes", async () => {
    fakeApi({
      [ENTITY]: [json(makeEntity({ attributes: { years: 8, "primary use": "backend" } }))],
      [EDGES]: [json([])],
    });
    renderAt("/knowledge/3");
    expect(await screen.findByRole("heading", { level: 1, name: "Python" })).toBeInTheDocument();
    expect(screen.getByText("skill")).toBeInTheDocument();
    expect(screen.getByText("confirmed")).toBeInTheDocument();
    expect(screen.getByText("General-purpose programming language.")).toBeInTheDocument();
    const term = screen.getByText("primary use");
    expect(term.tagName).toBe("DT");
    expect(term.nextElementSibling).toHaveTextContent("backend");
    expect(screen.getByText("8").tagName).toBe("DD");
    expect(await screen.findByText("No relationships recorded.")).toBeInTheDocument();
  });

  it("lists edges: self as plain text, the other end as a link, note and confidence", async () => {
    fakeApi({
      [ENTITY]: [json(makeEntity())],
      [EDGES]: [
        json([
          makeEdge({ note: "Daily use", confidence: 0.9 }),
          makeEdge({ id: 8, src_id: 5, dst_id: 3, rel: "requires" }),
        ]),
      ],
      "GET /api/entities/4": [json(makeEntity({ id: 4, name: "Example Corp" }))],
      "GET /api/entities/5": [json(makeEntity({ id: 5, name: "Backend role" }))],
    });
    renderAt("/knowledge/3");
    const first = (await screen.findByText("used_in")).closest("li") as HTMLElement;
    expect(within(first).getByText("Python")).toBeInTheDocument();
    expect(within(first).queryByRole("link", { name: "Python" })).toBeNull();
    expect(await within(first).findByRole("link", { name: "Example Corp" })).toHaveAttribute(
      "href",
      "/knowledge/4",
    );
    expect(within(first).getByText("Daily use")).toBeInTheDocument();
    expect(within(first).getByText("confidence 0.9")).toBeInTheDocument();
    const second = screen.getByText("requires").closest("li") as HTMLElement;
    expect(await within(second).findByRole("link", { name: "Backend role" })).toHaveAttribute(
      "href",
      "/knowledge/5",
    );
    expect(within(second).queryByText(/confidence/)).toBeNull();
  });

  it("falls back to an entity number when the other end cannot be loaded", async () => {
    fakeApi({
      [ENTITY]: [json(makeEntity())],
      [EDGES]: [json([makeEdge()])],
      "GET /api/entities/4": [json({ detail: "missing" }, 404)],
    });
    renderAt("/knowledge/3");
    expect(await screen.findByRole("link", { name: "Entity 4" })).toHaveAttribute(
      "href",
      "/knowledge/4",
    );
  });

  it("shows Entity not found with a link back on 404", async () => {
    fakeApi({
      [ENTITY]: [json({ detail: "nope" }, 404)],
      [EDGES]: [json({}, 404)],
    });
    renderAt("/knowledge/3");
    expect(await screen.findByText("Entity not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to knowledge/ })).toHaveAttribute(
      "href",
      "/knowledge",
    );
  });

  it("shows an error for other entity failures", async () => {
    fakeApi({ [ENTITY]: [json({ detail: "boom" }, 500)], [EDGES]: [json([])] });
    renderAt("/knowledge/3");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load entity");
  });

  it("treats a non-numeric id as not found without fetching", () => {
    const api = fakeApi({});
    renderAt("/knowledge/abc");
    expect(screen.getByText("Entity not found")).toBeInTheDocument();
    expect(api.fn).not.toHaveBeenCalled();
  });

  it("keeps the entity visible when the edges fetch fails", async () => {
    fakeApi({
      [ENTITY]: [json(makeEntity())],
      [EDGES]: [json({ detail: "boom" }, 500)],
    });
    renderAt("/knowledge/3");
    expect(await screen.findByRole("heading", { level: 1, name: "Python" })).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load relationships");
  });

  it("renders hostile summary and attributes as text", async () => {
    fakeApi({
      [ENTITY]: [
        json(
          makeEntity({
            summary: "<script>alert(1)</script>",
            attributes: { "<b>k</b>": "<img src=x onerror=alert(1)>" },
          }),
        ),
      ],
      [EDGES]: [json([])],
    });
    const { container } = renderAt("/knowledge/3");
    expect(await screen.findByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(container.querySelector("img, b, script")).toBeNull();
  });

  it("opens the entity drawer from the why button and the edge drawer from an edge", async () => {
    const api = fakeApi({
      [ENTITY]: [json(makeEntity())],
      [EDGES]: [json([makeEdge()])],
      "GET /api/entities/4": [json(makeEntity({ id: 4, name: "Example Corp" }))],
      "GET /api/provenance/entity/3": [json([makeProvenance()])],
      "GET /api/provenance/edge/7": [json([makeProvenance({ excerpt: "Edge excerpt" })])],
    });
    renderAt("/knowledge/3");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Why do we know this?" }));
    expect(await screen.findByText("I used Python daily at Example Corp.")).toBeInTheDocument();
    expect(api.calls("GET /api/provenance/entity/3")).toHaveLength(1);
    await user.keyboard("{Escape}");
    await user.click(await screen.findByRole("button", { name: "Why: used_in Example Corp" }));
    expect(await screen.findByText("Edge excerpt")).toBeInTheDocument();
    expect(api.calls("GET /api/provenance/edge/7")).toHaveLength(1);
  });

  it("gives each edge's why button a distinguishing accessible name", async () => {
    fakeApi({
      [ENTITY]: [json(makeEntity())],
      [EDGES]: [json([makeEdge(), makeEdge({ id: 8, src_id: 5, dst_id: 3, rel: "requires" })])],
      "GET /api/entities/4": [json(makeEntity({ id: 4, name: "Example Corp" }))],
      "GET /api/entities/5": [json(makeEntity({ id: 5, name: "Backend role" }))],
    });
    renderAt("/knowledge/3");
    expect(
      await screen.findByRole("button", { name: "Why: used_in Example Corp" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Why: requires Backend role" }),
    ).toBeInTheDocument();
  });

  it("closes the drawer and shows no stale provenance when the route moves to another entity", async () => {
    const api = fakeApi({
      [ENTITY]: [json(makeEntity())],
      [EDGES]: [json([makeEdge()])],
      "GET /api/entities/4": [json(makeEntity({ id: 4, name: "Example Corp", summary: null }))],
      "GET /api/entities/4/edges": [json([])],
      "GET /api/provenance/entity/3": [json([makeProvenance({ excerpt: "Only about Python" })])],
      "GET /api/provenance/entity/4": [json([makeProvenance({ excerpt: "About Example Corp" })])],
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
          <Route path="/knowledge/:id" element={<EntityPage />} />
        </Routes>
      </>,
      { route: "/knowledge/3" },
    );
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Why do we know this?" }));
    expect(await screen.findByText("Only about Python")).toBeInTheDocument();
    // Entity 4 is already cached by the edge row, so the page swaps without a loading state.
    await waitFor(() => expect(api.calls("GET /api/entities/4")).toHaveLength(1));
    await act(async () => undefined);
    act(() => go("/knowledge/4"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Example Corp", hidden: true }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Only about Python")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("has no mutation controls", async () => {
    fakeApi({ [ENTITY]: [json(makeEntity())], [EDGES]: [json([])] });
    renderAt("/knowledge/3");
    await screen.findByRole("heading", { level: 1, name: "Python" });
    expect(screen.queryByRole("button", { name: /accept|edit|reject|delete/i })).toBeNull();
  });
});
