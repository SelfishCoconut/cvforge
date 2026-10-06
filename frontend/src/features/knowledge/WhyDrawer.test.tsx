import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../../test-utils";
import { makeProvenance } from "../../test/knowledge";
import { fakeApi } from "../review/fakeApi";
import { json } from "../review/fixtures";
import { WhyDrawer } from "./WhyDrawer";

afterEach(() => vi.unstubAllGlobals());

function Harness({ kind = "entity", id = 3 }: { kind?: "entity" | "edge"; id?: number }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>open why</button>
      <WhyDrawer kind={kind} id={id} open={open} onOpenChange={setOpen} />
    </>
  );
}

async function open() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "open why" }));
  return user;
}

describe("WhyDrawer", () => {
  it("does not fetch while closed", () => {
    const api = fakeApi({});
    renderApp(<Harness />);
    expect(api.fn).not.toHaveBeenCalled();
  });

  it("shows source, locator, literal excerpt in a blockquote and field/value", async () => {
    const api = fakeApi({
      "GET /api/provenance/entity/3": [
        json([
          makeProvenance(),
          makeProvenance({
            assertion_id: 2,
            source_kind: "document",
            source_label: "cv.pdf",
            locator: "page:2",
            excerpt: "Led a team of 4.",
            field: "team_size",
            value: 4,
          }),
        ]),
      ],
    });
    renderApp(<Harness />);
    await open();
    const dialog = await screen.findByRole("dialog", {
      name: "Why do we know this?",
    });
    const quotes = await screen.findAllByRole("blockquote");
    expect(quotes[0]).toHaveTextContent("I used Python daily at Example Corp.");
    expect(quotes[0]?.className).toContain("font-display");
    expect(dialog).toHaveTextContent("chat");
    expect(dialog).toHaveTextContent("Chat 2026-09-01");
    expect(screen.getByText("message:4").className).toContain("font-mono");
    expect(dialog).toHaveTextContent("team_size");
    expect(dialog).toHaveTextContent("4");
    expect(api.calls("GET /api/provenance/entity/3")).toHaveLength(1);
  });

  it("uses the edge endpoint for edges", async () => {
    const api = fakeApi({
      "GET /api/provenance/edge/7": [json([makeProvenance()])],
    });
    renderApp(<Harness kind="edge" id={7} />);
    await open();
    expect(await screen.findByRole("blockquote")).toBeInTheDocument();
    expect(api.calls("GET /api/provenance/edge/7")).toHaveLength(1);
  });

  it("explains a 404 as missing evidence", async () => {
    fakeApi({
      "GET /api/provenance/entity/3": [json({ detail: "none" }, 404)],
    });
    renderApp(<Harness />);
    await open();
    expect(await screen.findByText("No evidence is recorded for this item.")).toBeInTheDocument();
  });

  it("shows other failures as an error", async () => {
    fakeApi({
      "GET /api/provenance/entity/3": [json({ detail: "boom" }, 500)],
    });
    renderApp(<Harness />);
    await open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load evidence");
  });

  it("shows loading while pending", async () => {
    fakeApi({
      "GET /api/provenance/entity/3": [() => new Promise<Response>(() => {})],
    });
    renderApp(<Harness />);
    await open();
    expect(await screen.findByText("Loading evidence…")).toBeInTheDocument();
  });

  it("renders hostile excerpts literally as text", async () => {
    const hostile = '<img src=x onerror="alert(1)"><script>x</script>';
    fakeApi({
      "GET /api/provenance/entity/3": [json([makeProvenance({ excerpt: hostile })])],
    });
    renderApp(<Harness />);
    await open();
    const quote = await screen.findByRole("blockquote");
    expect(quote.textContent).toBe(hostile);
    expect(quote.querySelector("img, script")).toBeNull();
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    fakeApi({ "GET /api/provenance/entity/3": [json([makeProvenance()])] });
    renderApp(<Harness />);
    const user = await open();
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "open why" })).toHaveFocus());
  });
});
