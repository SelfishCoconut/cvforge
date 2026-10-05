# Benchmarks

## Chat round-trip latency (NFR-10)

The conversational round-trip — a message submitted, a proposal returned — must
stay under 30 s at p95 on `qwen3.6:27b` running locally.

```
uv run python scripts/bench/latency.py            # one pass over 20 messages
uv run python scripts/bench/latency.py --runs 3   # more samples
```

The script drives the real pipeline (chat endpoint, agent, intake) against your
local Ollama with an empty in-memory knowledge base, prints p50 and p95, and exits
1 if p95 exceeds 30 s. It refuses to run (exit 2) against an external provider or a
non-loopback endpoint, so a cloud model can never be measured against this target.

It is **not** part of `make test` or CI: unit, integration and golden tests never
call a live model (NFR-08). Record each run by hand in `docs/sanity/` with the model
and machine, so a regression is visible over time.

The fixture messages are synthetic: `scripts/bench/fixtures/messages.txt`.
