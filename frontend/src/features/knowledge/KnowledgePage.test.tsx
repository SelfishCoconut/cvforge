import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../../test-utils";
import { LocationProbe } from "../../test/LocationProbe";
import { makeEntity } from "../../test/knowledge";
import { fakeApi } from "../review/fakeApi";
import { json } from "../review/fixtures";
import { KnowledgePage } from "./KnowledgePage";

const ALL = "GET /api/entities";
const GAPS = "GET /api/entities?kind=skill&state=gap";

afterEach(() => vi.unstubAllGlobals());

function page() {
  return (
    <>
      <KnowledgePage />
      <LocationProbe />
    </>
  );
}

describe("KnowledgePage", () => {
  it("fetches without params first and lists rows linking to the entity", async () => {
    const api = fakeApi({
      [ALL]: [json([makeEntity(), makeEntity({ id: 9, name: "Rust", state: "learning" })])],
    });
    renderApp(page(), { route: "/knowledge" });
    expect(screen.getByRole("heading", { level: 1, name: "Knowledge" })).toBeInTheDocument();
    const link = await screen.findByRole("link", { name: /Python/ });
    expect(link).toHaveAttribute("href", "/knowledge/3");
    expect(link).toHaveTextContent("skill");
    expect(link).toHaveTextContent("confirmed");
    expect(screen.getByRole("link", { name: /Rust/ })).toHaveTextContent("learning");
    expect(api.calls(ALL)).toHaveLength(1);
  });

  it("refetches with the chosen filters and keeps them in the URL", async () => {
    const api = fakeApi({
      [ALL]: [json([makeEntity()])],
      "GET /api/entities?kind=skill": [json([makeEntity()])],
      [GAPS]: [json([makeEntity({ id: 12, name: "Kubernetes", state: "gap" })])],
    });
    renderApp(page(), { route: "/knowledge" });
    await screen.findByRole("link", { name: /Python/ });
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Kind"), "skill");
    await user.selectOptions(screen.getByLabelText("State"), "gap");
    expect(await screen.findByRole("link", { name: /Kubernetes/ })).toBeInTheDocument();
    expect(api.calls(GAPS)).toHaveLength(1);
    expect(screen.getByTestId("location")).toHaveTextContent("/knowledge?kind=skill&state=gap");
    await user.selectOptions(screen.getByLabelText("State"), "All");
    expect(screen.getByTestId("location")).toHaveTextContent("/knowledge?kind=skill");
  });

  it("reads filters from the URL and offers every vocabulary value plus All", async () => {
    const api = fakeApi({ [GAPS]: [json([])] });
    renderApp(page(), { route: "/knowledge?kind=skill&state=gap" });
    expect(await screen.findByText("No entities match.")).toBeInTheDocument();
    expect(screen.getByLabelText("Kind")).toHaveValue("skill");
    expect(screen.getByLabelText("State")).toHaveValue("gap");
    const kinds = screen.getByLabelText("Kind").querySelectorAll("option");
    expect([...kinds].map((o) => o.textContent)).toEqual([
      "All",
      "skill",
      "project",
      "organization",
      "role",
      "education",
      "credential",
      "achievement",
      "responsibility",
    ]);
    const states = screen.getByLabelText("State").querySelectorAll("option");
    expect([...states].map((o) => o.textContent)).toEqual([
      "All",
      "confirmed",
      "learning",
      "gap",
      "archived",
    ]);
    expect(api.calls(GAPS)).toHaveLength(1);
  });

  it("ignores unknown filter values and does not send them", async () => {
    const api = fakeApi({ [ALL]: [json([makeEntity()])] });
    renderApp(page(), { route: "/knowledge?kind=bogus&state=nope" });
    await screen.findByRole("link", { name: /Python/ });
    expect(api.fn).toHaveBeenCalledTimes(1);
    expect(api.calls(ALL)).toHaveLength(1);
    expect(screen.getByLabelText("Kind")).toHaveValue("");
  });

  it("shows an error state", async () => {
    fakeApi({ [ALL]: [json({ detail: "boom" }, 500)] });
    renderApp(page(), { route: "/knowledge" });
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load entities");
  });

  it("shows a loading state", () => {
    fakeApi({ [ALL]: [json([])] });
    renderApp(page(), { route: "/knowledge" });
    expect(screen.getByText("Loading entities…")).toBeInTheDocument();
  });

  it("renders hostile names as text", async () => {
    fakeApi({
      [ALL]: [
        json([
          makeEntity({
            name: '<img src=x onerror="alert(1)">' + "A".repeat(80),
          }),
        ]),
      ],
    });
    const { container } = renderApp(page(), { route: "/knowledge" });
    await screen.findByRole("link", { name: /<img src=x/ });
    expect(container.querySelector("img")).toBeNull();
  });

  it("has no mutation controls", async () => {
    fakeApi({ [ALL]: [json([makeEntity()])] });
    renderApp(page(), { route: "/knowledge" });
    await screen.findByRole("link", { name: /Python/ });
    expect(screen.queryByRole("button", { name: /accept|edit|reject|delete/i })).toBeNull();
  });
});
