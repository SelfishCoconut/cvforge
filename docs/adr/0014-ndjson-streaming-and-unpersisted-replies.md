# 0014. Chat streams as NDJSON over a POST, and assistant replies are not persisted

Date: 2026-10-05
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-13 asks for the assistant's reply to appear as it is generated. The chat
endpoint (ADR-0013 part 2) is a POST with a body, and a stream that fails or is
abandoned part-way must not leave a half-written proposal (invariant 4).

## Decision

**D-E — the transport is NDJSON over `POST /api/chat/messages/stream`**
(`application/x-ndjson`), one JSON object per line: `delta` (growth of the reply),
`proposal` (the stored proposal, rejected items and ids), `done`; or `error`, after
which the stream ends. The browser reads it with `fetch` and a `ReadableStream`.

- The size, whitespace and conversation checks, and the storing of the message as
  evidence, happen *before* the stream starts, so they are ordinary 422/404
  responses rather than in-stream errors.
- Streaming shares `_store_message` and `_finish` with the non-streaming route;
  nothing is stored as a proposal until the whole output has validated.
- `run_stream()` does not retry an invalid final output (pydantic-ai raises
  `UnexpectedModelBehavior`), so on this path an invalid final output is an `error`
  event, not a retry. The non-streaming route keeps its retries.
- The agent runs in its own task feeding a queue. Closing the response (a client
  disconnect) cancels that task; yielding from inside pydantic-ai's `run_stream`
  context and then closing the generator makes it raise `RuntimeError` instead of
  exiting.

**D-F — assistant replies are not persisted in M1; user messages are, as evidence.**
Only the user's own words are citable facts (FR-12). Persisting replies would need a
chat-history table and a second registered writer with no requirement behind it.

## Alternatives considered

- **Server-sent events.** Rejected: `EventSource` cannot POST a body.
- **WebSockets.** Rejected: a second protocol for one-way output.
- **Stream the reply from a separate call after the proposal is stored.** Rejected:
  two model calls, and the reply could disagree with the proposal.

## Consequences

- Not verified against a live model: tool-output streaming needs the model to
  stream tool arguments. If a real Ollama run shows it does not, fall back to
  `NativeOutput`/`PromptedOutput` and amend this ADR.
- A reload loses the conversation transcript (only the user's messages survive).
