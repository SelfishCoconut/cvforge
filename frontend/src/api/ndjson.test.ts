import { describe, expect, it } from "vitest";
import { streamOf, streamOfBytes } from "../test-utils";
import { readChatEvents, readNdjson, StreamError } from "./ndjson";

const enc = new TextEncoder();

async function collect<T>(it: AsyncIterable<T>): Promise<T[]> {
  const out: T[] = [];
  for await (const x of it) out.push(x);
  return out;
}

describe("readNdjson", () => {
  it("parses one object per line", async () => {
    const out = await collect(readNdjson(streamOf(['{"a":1}\n{"a":2}\n'])));
    expect(out).toEqual([{ a: 1 }, { a: 2 }]);
  });

  it("reassembles a line split across chunks", async () => {
    const out = await collect(readNdjson(streamOf(['{"a":', '1}\n{"a"', ":2}\n"])));
    expect(out).toEqual([{ a: 1 }, { a: 2 }]);
  });

  it("reassembles a multi-byte char split across chunks", async () => {
    const bytes = enc.encode('{"t":"é"}\n');
    const at = bytes.indexOf(0xc3) + 1; // between the two bytes of 'é'
    expect(bytes[at]).toBe(0xa9);
    const out = await collect(readNdjson(streamOfBytes([bytes.slice(0, at), bytes.slice(at)])));
    expect(out).toEqual([{ t: "é" }]);
  });

  it("accepts a final line without a trailing newline", async () => {
    const out = await collect(readNdjson(streamOf(['{"a":1}\n{"a":2}'])));
    expect(out).toEqual([{ a: 1 }, { a: 2 }]);
  });

  it("skips blank lines", async () => {
    const out = await collect(readNdjson(streamOf(['\n{"a":1}\n\n  \n{"a":2}\n'])));
    expect(out).toEqual([{ a: 1 }, { a: 2 }]);
  });

  it("throws StreamError when the stream is cut mid-object", async () => {
    const seen: unknown[] = [];
    await expect(
      (async () => {
        for await (const x of readNdjson(streamOf(['{"a":1}\n{"a":']))) seen.push(x);
      })(),
    ).rejects.toBeInstanceOf(StreamError);
    expect(seen).toEqual([{ a: 1 }]);
  });

  it("throws StreamError on a malformed complete line", async () => {
    await expect(collect(readNdjson(streamOf(["not json\n"])))).rejects.toBeInstanceOf(
      StreamError,
    );
  });

  it("throws StreamError when the response has no body", async () => {
    await expect(collect(readNdjson(new Response(null)))).rejects.toBeInstanceOf(StreamError);
  });
});

describe("readChatEvents", () => {
  it("throws StreamError carrying the message on an error event", async () => {
    const res = streamOf(['{"type":"delta","text":"hi"}\n{"type":"error","message":"boom"}\n']);
    await expect(collect(readChatEvents(res))).rejects.toThrow("boom");
  });

  it("throws StreamError when the stream ends without done", async () => {
    const res = streamOf(['{"type":"delta","text":"hi"}\n']);
    await expect(collect(readChatEvents(res))).rejects.toBeInstanceOf(StreamError);
  });

  it("stops after done", async () => {
    const res = streamOf(['{"type":"delta","text":"hi"}\n{"type":"done"}\n{"type":"delta","text":"x"}\n']);
    const out = await collect(readChatEvents(res));
    expect(out).toEqual([{ type: "delta", text: "hi" }, { type: "done" }]);
  });
});
