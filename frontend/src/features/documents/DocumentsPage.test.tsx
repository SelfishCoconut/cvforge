import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DocumentView, ExtractionView } from "../../api/types";
import { renderApp } from "../../test-utils";
import { fakeApi } from "../review/fakeApi";
import { json } from "../review/fixtures";
import { DocumentsPage } from "./DocumentsPage";

const UPLOAD = "POST /api/documents";
const EXTRACT = "POST /api/documents/7/extract";

afterEach(() => vi.unstubAllGlobals());

const doc: DocumentView = {
  source_id: 7,
  filename: "cv.pdf",
  pages: 2,
  characters: 1234,
};

function extraction(over: Partial<ExtractionView> = {}): ExtractionView {
  return {
    source_id: 7,
    chunks: 1,
    proposal: {
      id: 9,
      operations: [
        {
          id: 1,
          seq: 0,
          op_type: "create_entity",
          payload: { op_type: "create_entity" },
          classification: "new",
          target_kind: null,
          target_id: null,
        },
      ],
    },
    rejected: [],
    similarity_available: true,
    ...over,
  };
}

/** Pick `file`; `anyType` models choosing "All files" in the picker, past the `accept` filter. */
async function upload(
  file = new File(["x"], "cv.pdf", { type: "application/pdf" }),
  anyType = false,
) {
  const user = userEvent.setup({ applyAccept: !anyType });
  await user.upload(screen.getByLabelText("Document"), file);
}

describe("DocumentsPage", () => {
  it("explains itself and offers a file picker for the four formats", () => {
    fakeApi({});
    renderApp(<DocumentsPage />);
    expect(screen.getByRole("heading", { level: 1, name: "Documents" })).toBeInTheDocument();
    expect(screen.getByLabelText("Document")).toHaveAttribute("accept", ".pdf,.docx,.md,.txt");
    expect(screen.getByText(/nothing is saved until you review it/)).toBeInTheDocument();
  });

  it("uploads the chosen file as multipart form data and lists it", async () => {
    const api = fakeApi({ [UPLOAD]: [json(doc, 201)] });
    renderApp(<DocumentsPage />);
    await upload();
    expect(await screen.findByRole("heading", { level: 2, name: "cv.pdf" })).toBeInTheDocument();
    expect(screen.getByText(/2 pages, 1,234\s+characters/)).toBeInTheDocument();
    const init = api.calls(UPLOAD)[0]?.[1];
    expect(init?.body).toBeInstanceOf(FormData);
    expect((init?.body as FormData).get("file")).toBeInstanceOf(File);
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
  });

  it("shows the server's reason when an upload is refused", async () => {
    fakeApi({ [UPLOAD]: [json({ detail: ".exe is not supported" }, 415)] });
    renderApp(<DocumentsPage />);
    await upload(new File(["x"], "setup.exe"), true);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not upload: .exe is not supported",
    );
  });

  it("extracts facts and links to the review of the new proposal", async () => {
    fakeApi({ [UPLOAD]: [json(doc, 201)], [EXTRACT]: [json(extraction())] });
    renderApp(<DocumentsPage />);
    await upload();
    await userEvent.click(await screen.findByRole("button", { name: "Extract facts" }));
    const link = await screen.findByRole("link", { name: "Review them" });
    expect(link).toHaveAttribute("href", "/review/9");
    expect(screen.getByText(/Proposed 1 change\./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Extract facts" })).toBeDisabled();
  });

  it("says a long read is expected while extraction runs", async () => {
    let finish: (r: Response) => void = () => undefined;
    const pending = () => new Promise<Response>((resolve) => (finish = resolve));
    fakeApi({ [UPLOAD]: [json(doc, 201)], [EXTRACT]: [pending] });
    renderApp(<DocumentsPage />);
    await upload();
    await userEvent.click(await screen.findByRole("button", { name: "Extract facts" }));
    expect(await screen.findByRole("status")).toHaveTextContent(/several minutes/);
    finish(json(extraction()));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Review them" })).toBeInTheDocument(),
    );
  });

  it("reports dropped items and a missing similarity index", async () => {
    const result = extraction({
      similarity_available: false,
      rejected: [{ item: "fact 'c0:k'", reason: "no resolvable locator" }],
    });
    fakeApi({ [UPLOAD]: [json(doc, 201)], [EXTRACT]: [json(result)] });
    renderApp(<DocumentsPage />);
    await upload();
    await userEvent.click(await screen.findByRole("button", { name: "Extract facts" }));
    expect(await screen.findByText("fact 'c0:k': no resolvable locator")).toBeInTheDocument();
    expect(screen.getByText(/Duplicate detection was unavailable/)).toBeInTheDocument();
  });

  it("says so when nothing was found, with no review link", async () => {
    const empty = extraction({ proposal: { id: null, operations: [] } });
    fakeApi({ [UPLOAD]: [json(doc, 201)], [EXTRACT]: [json(empty)] });
    renderApp(<DocumentsPage />);
    await upload();
    await userEvent.click(await screen.findByRole("button", { name: "Extract facts" }));
    expect(await screen.findByText("No facts were found in this document.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review them" })).not.toBeInTheDocument();
  });

  it("shows a failed extraction and lets the user try again", async () => {
    fakeApi({
      [UPLOAD]: [json(doc, 201)],
      [EXTRACT]: [json({ detail: "the model could not process the document: down" }, 502)],
    });
    renderApp(<DocumentsPage />);
    await upload();
    await userEvent.click(await screen.findByRole("button", { name: "Extract facts" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/model could not process/);
    expect(screen.getByRole("button", { name: "Extract facts" })).toBeEnabled();
  });

  it("uses the singular for a one-page, one-change result", async () => {
    fakeApi({
      [UPLOAD]: [json({ ...doc, pages: 1 }, 201)],
      [EXTRACT]: [json(extraction())],
    });
    renderApp(<DocumentsPage />);
    await upload();
    expect(await screen.findByText(/1 page,/)).toBeInTheDocument();
  });
});
