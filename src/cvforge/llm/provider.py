"""Build a Pydantic AI model from the persisted provider settings (FR-38, spec §5, §2 D5).

Local-first by default (NFR-01): Ollama needs no opt-in. Anthropic and OpenAI
each need `allow_external=True` before `build_model` will even look at
`api_key_env` — the refusal happens before any client is constructed, so an
external provider is never one flag-flip away from a live call. `build_model`
always re-reads the settings (FR-39): a change persisted by `save_settings`
takes effect on the very next call, with no restart.
"""

import os
from collections.abc import Mapping

import sqlalchemy as sa
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from cvforge.kb.vocab import Provider
from cvforge.llm.settings_store import ProviderSettings, load_settings

EXTERNAL = frozenset({Provider.ANTHROPIC, Provider.OPENAI})


class ExternalProviderDisabledError(Exception):
    """The persisted settings name Anthropic or OpenAI without `allow_external` (NFR-01)."""


class MissingApiKeyError(Exception):
    """`api_key_env` is unset, or names an environment variable that isn't."""


def build_model(engine: sa.Engine, *, environ: Mapping[str, str] = os.environ) -> Model:
    """Build a model handle for the currently persisted provider.

    Args:
        engine: The knowledge-base engine, where settings are persisted.
        environ: Where to read the API key from, by the name in
            `settings.api_key_env`. Defaults to the real process environment;
            tests pass a fake mapping so nothing here ever needs a real secret.

    Returns:
        A model handle. Constructing it makes no network call.

    Raises:
        ExternalProviderDisabledError: If the settings name Anthropic or OpenAI
            without `allow_external`.
        MissingApiKeyError: If an external provider's `api_key_env` is unset, or
            names a variable that is not set.
    """
    settings = load_settings(engine, environ=environ)
    if settings.provider in EXTERNAL and not settings.allow_external:
        raise ExternalProviderDisabledError(
            f"{settings.provider} is an external provider; set allow_external to use it (NFR-01)"
        )
    if settings.provider is Provider.OLLAMA:
        return _ollama(settings)
    api_key = _read_api_key(settings, environ)
    if settings.provider is Provider.ANTHROPIC:
        return AnthropicModel(settings.model, provider=AnthropicProvider(api_key=api_key))
    return OpenAIChatModel(settings.model, provider=OpenAIProvider(api_key=api_key))


def _ollama(settings: ProviderSettings) -> Model:
    # The stored base_url stays the bare host (e.g. http://127.0.0.1:11434):
    # embeddings call {base_url}/api/embed, so only this call site adds /v1.
    base_url = (settings.base_url or "http://127.0.0.1:11434").rstrip("/")
    return OllamaModel(settings.model, provider=OllamaProvider(base_url=f"{base_url}/v1"))


def _read_api_key(settings: ProviderSettings, environ: Mapping[str, str]) -> str:
    if not settings.api_key_env:
        raise MissingApiKeyError(
            f"{settings.provider} needs api_key_env set to the name of an environment variable"
        )
    key = environ.get(settings.api_key_env)
    if not key:
        raise MissingApiKeyError(f"environment variable {settings.api_key_env!r} is not set")
    return key
