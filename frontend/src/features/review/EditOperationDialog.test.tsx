import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "../../test-utils";
import { json, makeEvidence, makeOp } from "./fixtures";
import { OperationCard } from "./OperationCard";

type OnDecide = (
  decision: "accept" | "edit" | "reject",
  edited?: Record<string, unknown>,
) => Promise<string | null>;

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(json(makeEvidence()))),
  );
});
afterEach(() => vi.unstubAllGlobals());

function setup(op = makeOp(), result: string | null = null) {
  const onDecide = vi.fn<OnDecide>(() => Promise.resolve(result));
  renderApp(
    <OperationCard op={op} proposalOpen busy={false} error={null} onDecide={onDecide} />,
  );
  return { onDecide, user: userEvent.setup() };
}

async function openEditor(user: ReturnType<typeof userEvent.setup>, name = "Edit") {
  await user.click(screen.getByRole("button", { name }));
  return screen.getByRole("dialog", { name: "Edit operation" });
}

describe("EditOperationDialog", () => {
  it("opens with the current payload pretty-printed", async () => {
    const { user } = setup();
    await openEditor(user);
    expect(screen.getByLabelText("Payload (JSON)")).toHaveValue(
      JSON.stringify(makeOp().payload, null, 2),
    );
  });

  it("opens an edited operation with its edited payload, not the original", async () => {
    const edited = { op_type: "create_entity", name: "Senior backend engineer", evidence_id: 40 };
    const { user } = setup(makeOp({ status: "edited", edited_payload: edited }));
    await openEditor(user, "Edit again");
    expect(screen.getByLabelText("Payload (JSON)")).toHaveValue(JSON.stringify(edited, null, 2));
  });

  it.each([
    ["{not json", /Not valid JSON/],
    ["[1, 2]", /must be a JSON object/],
    ["42", /must be a JSON object/],
    ["null", /must be a JSON object/],
  ])("rejects %s inline and sends nothing", async (text, message) => {
    const { user, onDecide } = setup();
    await openEditor(user);
    const box = screen.getByLabelText("Payload (JSON)");
    await user.clear(box);
    await user.click(box);
    await user.paste(text);
    await user.click(screen.getByRole("button", { name: "Save edit" }));
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(box).toHaveAttribute("aria-invalid", "true");
    expect(onDecide).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("submits a valid object as an edit and closes", async () => {
    const { user, onDecide } = setup();
    await openEditor(user);
    const box = screen.getByLabelText("Payload (JSON)");
    await user.clear(box);
    await user.click(box);
    await user.paste('{"name": "Staff engineer", "evidence_id": 40}');
    await user.click(screen.getByRole("button", { name: "Save edit" }));
    expect(onDecide).toHaveBeenCalledWith("edit", { name: "Staff engineer", evidence_id: 40 });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("keeps the dialog and the typed text when the server refuses the edit", async () => {
    const { user } = setup(makeOp(), "payload is invalid");
    await openEditor(user);
    const box = screen.getByLabelText("Payload (JSON)");
    await user.clear(box);
    await user.click(box);
    await user.paste('{"name": "Staff engineer"}');
    await user.click(screen.getByRole("button", { name: "Save edit" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("payload is invalid");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(box).toHaveValue('{"name": "Staff engineer"}');
  });

  it("closes on Escape and on Cancel, returning focus to the Edit button", async () => {
    const { user, onDecide } = setup();
    await openEditor(user);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("button", { name: "Edit" })).toHaveFocus();
    await openEditor(user);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.getByRole("button", { name: "Edit" })).toHaveFocus();
    expect(onDecide).not.toHaveBeenCalled();
  });

  it("traps focus: Tab cycles inside the dialog", async () => {
    const { user } = setup();
    const dialog = await openEditor(user);
    for (let i = 0; i < 6; i += 1) {
      await user.tab();
      expect(dialog).toContainElement(document.activeElement as HTMLElement);
    }
    await user.tab({ shift: true });
    expect(dialog).toContainElement(document.activeElement as HTMLElement);
  });

  it("resets unsaved text when reopened", async () => {
    const { user } = setup();
    await openEditor(user);
    const box = screen.getByLabelText("Payload (JSON)");
    await user.clear(box);
    await user.paste("{bad");
    await user.click(screen.getByRole("button", { name: "Save edit" }));
    await user.keyboard("{Escape}");
    await openEditor(user);
    expect(screen.getByLabelText("Payload (JSON)")).toHaveValue(
      JSON.stringify(makeOp().payload, null, 2),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
