import { useCallback, useEffect, useReducer, useRef } from "react";
import { api } from "../../api/client";
import { readChatEvents } from "../../api/ndjson";
import type { RejectedView } from "../../api/types";

export type Turn =
  | { role: "user"; text: string }
  | {
      role: "assistant";
      text: string;
      status: "streaming" | "done" | "error";
      error?: string;
      proposalId?: number | null;
      rejected: RejectedView[];
      similarityAvailable?: boolean;
    };

type AssistantTurn = Extract<Turn, { role: "assistant" }>;

type Action =
  | { type: "start"; text: string }
  | { type: "delta"; text: string }
  | {
      type: "proposal";
      id: number | null;
      rejected: RejectedView[];
      similarity: boolean;
    }
  | { type: "finish"; status: "done" }
  | { type: "fail"; message: string };

/** Apply `patch` to the trailing assistant turn, if there is one. */
function patchLast(
  turns: Turn[],
  patch: (t: AssistantTurn) => AssistantTurn,
): Turn[] {
  const last = turns[turns.length - 1];
  if (last?.role !== "assistant") return turns;
  return [...turns.slice(0, -1), patch(last)];
}

function reduce(turns: Turn[], action: Action): Turn[] {
  switch (action.type) {
    case "start":
      return [
        ...turns,
        { role: "user", text: action.text },
        { role: "assistant", text: "", status: "streaming", rejected: [] },
      ];
    case "delta":
      return patchLast(turns, (t) => ({ ...t, text: t.text + action.text }));
    case "proposal":
      return patchLast(turns, (t) => ({
        ...t,
        proposalId: action.id,
        rejected: action.rejected,
        similarityAvailable: action.similarity,
      }));
    case "finish":
      return patchLast(turns, (t) =>
        t.status === "streaming" ? { ...t, status: "done" } : t,
      );
    case "fail":
      return patchLast(turns, (t) => ({
        ...t,
        status: "error",
        error: action.message,
      }));
  }
}

function describe(err: unknown): string {
  return err instanceof Error && err.message
    ? err.message
    : "something went wrong";
}

/** Chat transcript state plus a `send` that streams one assistant reply into it. */
export function useChatStream(): {
  turns: Turn[];
  busy: boolean;
  send: (text: string) => Promise<void>;
  cancel: () => void;
} {
  const [turns, dispatch] = useReducer(reduce, []);
  const conversationId = useRef<number | null>(null);
  const controller = useRef<AbortController | null>(null);

  const cancel = useCallback(() => controller.current?.abort(), []);
  useEffect(() => cancel, [cancel]);

  const send = useCallback(async (text: string) => {
    const ctl = new AbortController();
    controller.current = ctl;
    dispatch({ type: "start", text });
    try {
      const res = await api.streamChat(
        text,
        conversationId.current,
        ctl.signal,
      );
      for await (const e of readChatEvents(res)) {
        if (ctl.signal.aborted) break;
        if (e.type === "delta") dispatch({ type: "delta", text: e.text });
        else if (e.type === "proposal") {
          conversationId.current = e.conversation_id;
          dispatch({
            type: "proposal",
            id: e.proposal.id,
            rejected: e.rejected,
            similarity: e.similarity_available,
          });
        }
      }
      dispatch({ type: "finish", status: "done" });
    } catch (err) {
      // A deliberate cancel is not a failure; anything else (including a
      // TypeError from a reset connection) is shown, keeping the partial text.
      if (ctl.signal.aborted) dispatch({ type: "finish", status: "done" });
      else dispatch({ type: "fail", message: describe(err) });
    }
  }, []);

  const last = turns[turns.length - 1];
  const busy = last?.role === "assistant" && last.status === "streaming";
  return { turns, busy, send, cancel };
}
