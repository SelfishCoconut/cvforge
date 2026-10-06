import type { ChatEvent } from "./types";

/** The stream was cut, malformed, or reported a failure. */
export class StreamError extends Error {}

/** Yield one parsed JSON value per line of a newline-delimited JSON response body. */
export async function* readNdjson<T>(response: Response): AsyncIterable<T> {
  if (!response.body) throw new StreamError("response has no body");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const parse = (line: string): T => {
    try {
      return JSON.parse(line) as T;
    } catch {
      throw new StreamError("stream contained a malformed line");
    }
  };
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl = buffer.indexOf("\n");
      while (nl !== -1) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (line) yield parse(line);
        nl = buffer.indexOf("\n");
      }
    }
    buffer += decoder.decode();
    const rest = buffer.trim();
    if (rest) yield parse(rest);
  } finally {
    reader.releaseLock();
  }
}

/** Yield chat events until `done`; throw `StreamError` on an error event or a truncated stream. */
export async function* readChatEvents(response: Response): AsyncIterable<ChatEvent> {
  for await (const event of readNdjson<ChatEvent>(response)) {
    if (event.type === "error") throw new StreamError(event.message);
    yield event;
    if (event.type === "done") return;
  }
  throw new StreamError("the stream ended before the reply was complete");
}
