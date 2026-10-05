import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp, streamOf } from "../../test-utils";
import { ChatPage } from "./ChatPage";

const enc = new TextEncoder();
const line = (o: unknown): string => `${JSON.stringify(o)}\n`;
const delta = (text: string): string => line({ type: "delta", text });
const proposal = (over: Record<string, unknown> = {}): string =>
  line({
    type: "proposal",
    conversation_id: 3,
    message_id: 1,
    proposal: { id: 7, operations: [] },
    rejected: [],
    similarity_available: true,
    ...over,
  });
const done = line({ type: "done" });

function stubFetch(...responses: Response[]) {
  const fn = vi.fn();
  responses.forEach((r) => fn.mockResolvedValueOnce(r));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function bodyOf(fn: ReturnType<typeof vi.fn>, call = 0): unknown {
  const init = fn.mock.calls[call]?.[1] as RequestInit;
  return JSON.parse(init.body as string);
}

async function typeAndSend(text: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Message"), text);
  await user.click(screen.getByRole("button", { name: "Send" }));
  return user;
}

afterEach(() => vi.unstubAllGlobals());

describe("ChatPage", () => {
  it("posts the typed text with a null conversation id and shows it in the log", async () => {
    const fn = stubFetch(streamOf([delta("Hi"), done]));
    renderApp(<ChatPage />);
    await typeAndSend("Hello there");
    expect(fn.mock.calls[0]?.[0]).toBe("/api/chat/messages/stream");
    expect(bodyOf(fn)).toEqual({ text: "Hello there", conversation_id: null });
    const log = screen.getByRole("log");
    expect(within(log).getByText("Hello there")).toBeInTheDocument();
    expect(await within(log).findByText("Hi")).toBeInTheDocument();
  });

  it("submits on Ctrl+Enter and Cmd+Enter, newline on Enter, blank keeps Send disabled", async () => {
    const fn = stubFetch(
      streamOf([delta("a"), done]),
      streamOf([delta("b"), done]),
    );
    renderApp(<ChatPage />);
    const send = screen.getByRole("button", { name: "Send" });
    const box = screen.getByLabelText("Message");
    expect(send).toBeDisabled();
    const user = userEvent.setup();
    await user.type(box, "   ");
    expect(send).toBeDisabled();
    await user.clear(box);
    await user.type(box, "one{Enter}two");
    expect(box).toHaveValue("one\ntwo");
    expect(fn).not.toHaveBeenCalled();
    await user.keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(1));
    expect(bodyOf(fn)).toMatchObject({ text: "one\ntwo" });
    await waitFor(() => expect(send).toBeDisabled());
    await screen.findByText("a");
    await user.type(box, "three");
    await user.keyboard("{Meta>}{Enter}{/Meta}");
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2));
    await screen.findByText("b");
  });

  it("renders deltas incrementally in a polite live log", async () => {
    let ctl!: ReadableStreamDefaultController<Uint8Array>;
    stubFetch(
      new Response(
        new ReadableStream<Uint8Array>({
          start(c) {
            ctl = c;
          },
        }),
      ),
    );
    renderApp(<ChatPage />);
    const log = screen.getByRole("log");
    expect(log).toHaveAttribute("aria-live", "polite");
    await typeAndSend("go");
    ctl.enqueue(enc.encode(delta("Hel")));
    expect(await screen.findByText("Hel")).toBeInTheDocument();
    ctl.enqueue(enc.encode(delta("lo")));
    expect(await screen.findByText("Hello")).toBeInTheDocument();
    ctl.enqueue(enc.encode(done));
    ctl.close();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled(),
    );
  });

  it("links to the proposal when it has an id", async () => {
    stubFetch(streamOf([delta("ok"), proposal(), done]));
    renderApp(<ChatPage />);
    await typeAndSend("x");
    const link = await screen.findByRole("link", { name: "Review proposal" });
    expect(link).toHaveAttribute("href", "/review/7");
  });

  it("lists rejected items and shows no link when the proposal id is null", async () => {
    stubFetch(
      streamOf([
        delta("ok"),
        proposal({
          proposal: { id: null, operations: [] },
          rejected: [{ item: "Rust", reason: "no evidence" }],
        }),
        done,
      ]),
    );
    renderApp(<ChatPage />);
    await typeAndSend("x");
    expect(await screen.findByText("Rust — no evidence")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Review proposal" })).toBeNull();
  });

  it("warns when similarity search was unavailable", async () => {
    stubFetch(streamOf([proposal({ similarity_available: false }), done]));
    renderApp(<ChatPage />);
    await typeAndSend("x");
    expect(
      await screen.findByText(
        "Similarity search was unavailable; possible duplicates were not checked.",
      ),
    ).toBeInTheDocument();
  });

  it("shows an error event as an alert, keeps partial text and re-enables input", async () => {
    stubFetch(
      streamOf([
        delta("part"),
        line({ type: "error", message: "model fell over" }),
      ]),
    );
    renderApp(<ChatPage />);
    const user = await typeAndSend("x");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "model fell over",
    );
    expect(screen.getByText("part")).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toBeEnabled();
    await user.type(screen.getByLabelText("Message"), "y");
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("flags a stream that ends without done", async () => {
    stubFetch(streamOf([delta("cut")]));
    renderApp(<ChatPage />);
    await typeAndSend("x");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "the stream ended before the reply was complete",
    );
  });

  it("shows any thrown read error (TypeError) as an alert and keeps partial text", async () => {
    let pulls = 0;
    stubFetch(
      new Response(
        new ReadableStream<Uint8Array>({
          pull(c) {
            pulls += 1;
            if (pulls === 1) c.enqueue(enc.encode(delta("partial")));
            else c.error(new TypeError("network error"));
          },
        }),
      ),
    );
    renderApp(<ChatPage />);
    await typeAndSend("x");
    expect(await screen.findByRole("alert")).toHaveTextContent("network error");
    expect(screen.getByText("partial")).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toBeEnabled();
  });

  it("shows the server detail for an HTTP 422 and leaves nothing streaming", async () => {
    stubFetch(
      new Response(JSON.stringify({ detail: "message too long" }), {
        status: 422,
        headers: { "Content-Type": "application/json" },
      }),
    );
    renderApp(<ChatPage />);
    await typeAndSend("x");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "message too long",
    );
    expect(screen.getByLabelText("Message")).toBeEnabled();
    expect(screen.queryByText("…")).toBeNull();
  });

  it("sends the conversation id from the first proposal on the next message", async () => {
    const fn = stubFetch(
      streamOf([proposal({ conversation_id: 42 }), done]),
      streamOf([delta("two"), done]),
    );
    renderApp(<ChatPage />);
    const user = await typeAndSend("first");
    await screen.findByRole("link", { name: "Review proposal" });
    await user.type(screen.getByLabelText("Message"), "second");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(fn).toHaveBeenCalledTimes(2));
    expect(bodyOf(fn, 1)).toEqual({ text: "second", conversation_id: 42 });
  });

  it("aborts the fetch on unmount without showing an error", async () => {
    const fn = stubFetch(
      new Response(
        new ReadableStream<Uint8Array>({
          start(c) {
            c.enqueue(enc.encode(delta("x")));
          },
        }),
      ),
    );
    const { unmount } = renderApp(<ChatPage />);
    await typeAndSend("go");
    await screen.findByText("x");
    const signal = (fn.mock.calls[0]?.[1] as RequestInit).signal as AbortSignal;
    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
  });

  it("cancel stops the reply without an error", async () => {
    stubFetch(
      new Response(
        new ReadableStream<Uint8Array>({
          start(c) {
            c.enqueue(enc.encode(delta("x")));
          },
        }),
      ),
    );
    const user = userEvent.setup();
    renderApp(<ChatPage />);
    await user.type(screen.getByLabelText("Message"), "go");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("x");
    await user.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(screen.getByLabelText("Message")).toBeEnabled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders hostile reply text as literal text", async () => {
    const evil = "<img src=x onerror=alert(1)>";
    const long = "a".repeat(5000);
    const { container } = renderApp(<ChatPage />);
    stubFetch(
      streamOf([delta(evil), delta(` javascript:alert(1) ${long}`), done]),
    );
    await typeAndSend("x");
    expect(
      await screen.findByText(new RegExp("<img src=x onerror=alert\\(1\\)>")),
    ).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a[href^='javascript']")).toBeNull();
  });
});
