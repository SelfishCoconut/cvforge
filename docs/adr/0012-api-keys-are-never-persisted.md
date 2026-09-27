# 0012. API keys are never persisted; only the name of the environment variable that holds one

Date: 2026-09-27
Status: proposed — in force from 2026-09-27 under Álvaro's `/goal` delegation ("take
the necessary decisions"); not yet reviewed by him. Confirm to mark it accepted.

## Context

FR-39 requires provider settings — provider, model, base URL and "API-key
references" — to persist in the database, seeded from the environment on first
run, changeable at runtime. The word "references" leaves open whether that means
the key's value (encrypted or not) or something else, and M1b task B1.3
(`llm/settings_store.py`, `llm/provider.py`) had to pick one before the schema
could be written.

Two things make this database different from an ordinary application's config
store:

- NFR-09 requires a documented, portable export — `python -m cvforge.kb.export`
  copies the whole file, and the file itself is the thing Álvaro is told to back
  up and could reasonably share (a new machine, a support request, a bug report
  with an attached export).
- The repository, and by extension anything that ends up next to it or in a
  backup a user might paste into an issue, is public (design spec §2 D6).

A secret that persists in `app_setting` would therefore travel into every
export and every backup, and a database file is a far less obviously-sensitive
artifact to a user than a `.env` file — nothing about "here's my exported
knowledge base" signals "this also contains my Anthropic key."

## Decision

**`ProviderSettings.api_key_env` holds the NAME of an environment variable, never
a key's value.** `build_model()` resolves it at call time, from the real process
environment (or an injected mapping in tests). `save_settings`/`load_settings`
never see, and cannot write, an actual key. Selecting Anthropic or OpenAI
additionally requires `allow_external = true`, refused before any client is
constructed — a second gate independent of whether a key is even configured
(NFR-01).

The `/api/settings` read endpoint reflects this as `api_key_configured: bool`
(true only when the named variable both exists and currently resolves), never
the value itself. This is checked by a test that plants a real secret-shaped
value in a real environment variable and asserts it never appears in any
response body, row dump, or persisted column.

## Alternatives considered

- **Store the key, encrypted at rest with a locally-generated key.** Rejected.
  The encryption key would itself need to live somewhere — either the database
  (defeating the purpose) or a file next to it (recreating the same export/backup
  exposure one level down), for a local single-user tool where the OS's own file
  permissions on `data/` are the actual trust boundary already relied on
  elsewhere (the knowledge base itself is unencrypted, by the same reasoning).
- **Store the key in plaintext, rely on `data/` being gitignored.** Rejected.
  Gitignore protects against an accidental commit, not against the file being
  exported, backed up, or attached to a bug report — exactly the paths NFR-09
  exists to support.
- **A `.env`-only convention, no database column at all.** Rejected. FR-39
  requires the provider *chosen* to be runtime-changeable via `/settings`
  without a restart; the env var still needs a settings-row field to say
  *which* variable that provider's key lives in, even though the value itself
  never enters the row.

## Consequences

- Rotating or revoking a key never touches the knowledge base — it is purely an
  environment change, outside the app's write path entirely.
- An exported or backed-up `cvforge.db` is safe to attach to a bug report or
  copy to a new machine without a secondary "did I scrub the keys" step.
- The UI (M1c) must say, next to the `api_key_env` field, that it holds a name
  and not a value — `docs/guides/providers.md` states this for the API today.
- If a future provider's own SDK requires a key to be handed to it in a form
  other than an environment variable (a config file it insists on reading, say),
  `build_model()` is the one place that would need to adapt; the stored
  settings shape does not change.
