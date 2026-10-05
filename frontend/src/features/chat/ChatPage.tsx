import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { Message } from "./Message";
import { useChatStream } from "./useChatStream";

/** Streaming chat with the assistant; proposals it produces link to the review view. */
export function ChatPage() {
  const { turns, busy, send, cancel } = useChatStream();
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const blank = text.trim() === "";

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [turns]);

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (busy || blank) return;
    const value = text;
    setText("");
    void send(value);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex min-h-[calc(100dvh-14rem)] flex-col">
      <h1 className="text-3xl">Chat</h1>
      <div
        role="log"
        aria-label="Conversation"
        aria-live="polite"
        aria-relevant="additions text"
        className="mt-8 flex-1 space-y-6"
      >
        {turns.length === 0 && (
          <p className="max-w-prose text-ink-muted">
            Tell me about your work, projects or skills. I will propose what to
            add to your knowledge base; nothing is saved until you review it.
          </p>
        )}
        {turns.map((t, i) => (
          <Message key={i} turn={t} />
        ))}
        <div ref={end} />
      </div>
      <form
        onSubmit={submit}
        className="sticky bottom-0 mt-8 border-t border-line bg-surface pb-2 pt-4"
      >
        <label htmlFor="chat-message" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-message"
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          className="block w-full resize-y rounded-sm border border-line bg-card px-3 py-2 text-ink placeholder:text-ink-muted"
        />
        <div className="mt-3 flex items-center justify-between gap-4">
          <p className="text-sm text-ink-muted">Ctrl or Cmd + Enter to send</p>
          <div className="flex gap-3">
            {busy && (
              <button
                type="button"
                onClick={cancel}
                className="rounded-sm px-4 py-2 text-ink-muted ring-1 ring-inset ring-line hover:text-ink"
              >
                Stop
              </button>
            )}
            <button
              type="submit"
              disabled={busy || blank}
              className="rounded-sm bg-accent px-5 py-2 font-medium text-surface disabled:cursor-not-allowed disabled:opacity-40"
            >
              Send
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
