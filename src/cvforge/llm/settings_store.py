"""Persist the LLM provider configuration in the single `app_setting` row (FR-39).

Registered writer (ADR-0011): may write `app_setting`, nothing else. It is not
knowledge — no assertion, no evidence — so it does not go through `kb/apply.py`.
"""

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field

from cvforge.kb import schema
from cvforge.kb.vocab import Provider

ENV_PREFIX = "CVFORGE_LLM_"


class ProviderSettings(BaseModel):
    """The persisted, runtime-changeable configuration `build_model()` reads (FR-38, FR-39).

    Attributes:
        provider: Which LLM provider to build.
        model: The provider's model name.
        base_url: The provider's endpoint. Only meaningful for `ollama`.
        api_key_env: The NAME of an environment variable holding the API key —
            never the key itself (ADR-0012 decision D-B). `None` for `ollama`.
        allow_external: Must be `True` before `provider` may be `anthropic` or
            `openai` (NFR-01).
        embedding_provider: Which embedding backend to use. Only `"ollama"`
            exists in M1; a real pluggable interface arrives in M1b task B2.1.
        embedding_model: The embedding provider's model name.
        similarity_threshold: Minimum cosine similarity for a `duplicate` match
            (ADR-0012 decision D-G).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Provider = Provider.OLLAMA
    model: str = "qwen3.6:27b"
    base_url: str | None = "http://127.0.0.1:11434"
    api_key_env: str | None = None
    allow_external: bool = False
    embedding_provider: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    similarity_threshold: float = Field(default=0.85, ge=0, le=1)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _row_values(settings: ProviderSettings) -> dict[str, Any]:
    return {
        "provider": settings.provider.value,
        "model": settings.model,
        "base_url": settings.base_url,
        "api_key_env": settings.api_key_env,
        "allow_external": settings.allow_external,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "similarity_threshold": settings.similarity_threshold,
    }


def _from_row(row: sa.Row[Any]) -> ProviderSettings:
    return ProviderSettings(
        provider=Provider(row.provider),
        model=row.model,
        base_url=row.base_url,
        api_key_env=row.api_key_env,
        allow_external=bool(row.allow_external),
        embedding_provider=row.embedding_provider,
        embedding_model=row.embedding_model,
        similarity_threshold=row.similarity_threshold,
    )


def _seed_from_environ(environ: Mapping[str, str]) -> ProviderSettings:
    """Build the settings a first run seeds from `CVFORGE_LLM_*`; unset fields keep the default."""
    fields: dict[str, Any] = {}
    if (value := environ.get(f"{ENV_PREFIX}PROVIDER")) is not None:
        fields["provider"] = Provider(value)
    if (value := environ.get(f"{ENV_PREFIX}MODEL")) is not None:
        fields["model"] = value
    if (value := environ.get(f"{ENV_PREFIX}BASE_URL")) is not None:
        fields["base_url"] = value
    if (value := environ.get(f"{ENV_PREFIX}API_KEY_ENV")) is not None:
        fields["api_key_env"] = value
    if (value := environ.get(f"{ENV_PREFIX}ALLOW_EXTERNAL")) is not None:
        fields["allow_external"] = value.strip().lower() in {"1", "true", "yes", "on"}
    if (value := environ.get(f"{ENV_PREFIX}EMBEDDING_PROVIDER")) is not None:
        fields["embedding_provider"] = value
    if (value := environ.get(f"{ENV_PREFIX}EMBEDDING_MODEL")) is not None:
        fields["embedding_model"] = value
    if (value := environ.get(f"{ENV_PREFIX}SIMILARITY_THRESHOLD")) is not None:
        fields["similarity_threshold"] = float(value)
    return ProviderSettings(**fields)


def load_settings(
    engine: sa.Engine, *, environ: Mapping[str, str] = os.environ
) -> ProviderSettings:
    """Return the persisted provider settings, seeding them from the environment on first run only.

    Args:
        engine: The knowledge-base engine.
        environ: Read for `CVFORGE_LLM_*` variables the first time this ever
            runs against `engine`. Ignored on every later call — the database
            row is authoritative from the moment it exists (FR-39).

    Returns:
        The current settings.
    """
    with engine.begin() as conn:
        row = conn.execute(
            sa.select(schema.app_setting).where(schema.app_setting.c.id == 1)
        ).one_or_none()
        if row is not None:
            return _from_row(row)
        settings = _seed_from_environ(environ)
        conn.execute(
            sa.insert(schema.app_setting).values(id=1, updated_at=_now(), **_row_values(settings))
        )
        return settings


def save_settings(engine: sa.Engine, settings: ProviderSettings) -> ProviderSettings:
    """Persist `settings`, replacing whatever was stored.

    Args:
        engine: The knowledge-base engine.
        settings: The settings to persist.

    Returns:
        `settings`, unchanged, for convenient chaining.
    """
    with engine.begin() as conn:
        result = conn.execute(
            sa.update(schema.app_setting)
            .where(schema.app_setting.c.id == 1)
            .values(updated_at=_now(), **_row_values(settings))
        )
        if result.rowcount == 0:
            conn.execute(
                sa.insert(schema.app_setting).values(
                    id=1, updated_at=_now(), **_row_values(settings)
                )
            )
    return settings
