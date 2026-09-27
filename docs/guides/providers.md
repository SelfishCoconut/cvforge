# LLM providers

CVForge is local-first by default (NFR-01): with no configuration at all, it
talks only to a local Ollama endpoint. Anthropic and OpenAI are **opt-in** —
enabling either is a deliberate choice, made once per setting, never a
fallback the app reaches for on its own.

## Ollama (default, no opt-in needed)

| Setting | Default |
|---|---|
| `provider` | `ollama` |
| `model` | `qwen3.6:27b` |
| `base_url` | `http://127.0.0.1:11434` |

Nothing to enable. Point `base_url` at a different local Ollama instance if
yours doesn't run on the default port, and `model` at whichever model you have
pulled.

## Anthropic or OpenAI (opt-in)

Selecting either without opting in is refused with a `422` (via `/api/settings`)
or an `ExternalProviderDisabledError` (calling `build_model()` directly) —
**before** any network client is even constructed.

1. **Put the key in a real environment variable**, under whatever name you
   choose — CVForge never asks for the value itself.

   ```sh
   export MY_ANTHROPIC_KEY=sk-...   # any name; CVForge only ever stores this NAME
   ```

2. **Set the provider settings**, either through the API:

   ```sh
   curl -X PUT http://127.0.0.1:8000/api/settings -H 'Content-Type: application/json' -d '{
     "provider": "anthropic",
     "model": "claude-sonnet-5",
     "base_url": null,
     "api_key_env": "MY_ANTHROPIC_KEY",
     "allow_external": true,
     "embedding_provider": "ollama",
     "embedding_model": "nomic-embed-text",
     "similarity_threshold": 0.85
   }'
   ```

   or by seeding them from the environment on the very first run (before any
   settings row exists — every run after the first ignores these and reads the
   database instead):

   ```sh
   export CVFORGE_LLM_PROVIDER=openai
   export CVFORGE_LLM_MODEL=gpt-5.2
   export CVFORGE_LLM_API_KEY_ENV=MY_OPENAI_KEY
   export CVFORGE_LLM_ALLOW_EXTERNAL=true
   ```

`api_key_env` is **the name of the variable**, never the key. `GET
/api/settings` reflects this as `api_key_configured: true` once that named
variable both exists and holds a value — the key itself never appears in any
response, export, or backup (ADR-0012).

`allow_external` gates the provider *choice*; it is not itself a key. Both
`api_key_env` and `allow_external` must be set for `build_model()` to build
anything but Ollama.

## Embeddings

Only `ollama` (via `nomic-embed-text`) exists today. A pluggable
`EmbeddingProvider` interface arrives in M1b task B2.1; `embedding_provider` and
`embedding_model` are already persisted settings so that a future provider
needs no schema change.

## Web search

Not implemented yet (design spec §5, M3). It will follow the same pattern:
off by default, one explicit setting to turn on, no key stored in the
knowledge base.
