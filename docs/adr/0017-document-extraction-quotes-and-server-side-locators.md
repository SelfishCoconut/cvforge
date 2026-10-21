# 0017. The model quotes, the server locates: evidence locators for document facts

Date: 2026-10-21
Status: proposed — in force under Álvaro's `/goal` delegation; not yet reviewed by
him. Confirm to mark it accepted.

## Context

FR-15 requires every fact extracted from a document to carry a locator (page and
character span) that, sliced from the source text, reproduces the cited excerpt, and
requires a fact with no resolvable locator to be dropped. Local models are poor at
counting characters, and a document is untrusted input (NFR-07).

## Decision

**D-K — the agent returns a verbatim `excerpt` per fact and edge, never a position.**
`ingest/locators.resolve_excerpt` finds the quote in the stored page text (case-sensitive,
whitespace-insensitive) and the server builds `page:N chars:a-b` from the match. A quote
that is not in the document yields no locator; `llm.convert.to_payloads` rejects the item
with `no resolvable locator`, and its edges with it. So a locator reproduces its excerpt
by construction, and an invented quote cannot become a stored fact.

**D-L — the page is known, not asked for.** Each chunk lies on one page, so the server
supplies the page. The model is not asked for one, which removes a field it could get wrong.

**D-M — one conversion path.** `to_payloads` takes either one evidence id (chat) or a
function choosing evidence per item (documents), rather than a second converter.

**D-N — chunks of at most 3000 characters, split on paragraphs** (`ingest/chunking.py`),
because Ollama's default context window is 4096 tokens shared with the prompt, tool
schemas and reasoning (#123). A chunk's text is wrapped in `<document>` tags with a
closing tag inside it neutralised; the prompt tells the model it is data. The agent has
the same four read-only tools as the ingest agent and is registered in `AGENTS`, so the
read-only test covers it.

**D-O — results are merged across chunks before conversion.** Local ids are prefixed
per chunk so two chunks cannot collide, and a fact repeating an earlier one (same kind
and normalised name) is folded into it, so one proposal never contains two creates for
the same entity. Cross-document duplicates are the classifier's job (FR-16).

## Consequences

- A paraphrased quote is dropped even when the fact is true. That favours precision over
  recall, and the rejected items are returned to the caller so the loss is visible.
- A passage split across a chunk boundary can only be cited if the model quotes within
  one chunk.
- Re-running extraction over an unchanged document yields identical locators; the evidence
  rows repeat (one per run) but resolve to the same spans.
