"""FR-38: a pluggable LLM provider built from the persisted settings, without a live call."""

import pytest
import sqlalchemy as sa
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel

from cvforge.kb import schema
from cvforge.kb.vocab import Provider
from cvforge.llm.provider import (
    ExternalProviderDisabledError,
    MissingApiKeyError,
    build_model,
)
from cvforge.llm.settings_store import ProviderSettings, save_settings


def test_with_no_configuration_at_all_it_builds_a_local_ollama_model(kb: sa.Engine) -> None:
    model = build_model(kb, environ={})
    assert isinstance(model, OllamaModel)


def test_switching_the_persisted_provider_changes_the_next_model(
    kb: sa.Engine, canary: str
) -> None:
    save_settings(kb, ProviderSettings(provider=Provider.OLLAMA))
    first = build_model(kb, environ={})

    save_settings(
        kb,
        ProviderSettings(provider=Provider.OPENAI, model="m", allow_external=True, api_key_env="K"),
    )
    second = build_model(kb, environ={"K": canary})

    assert type(first) is not type(second)
    assert isinstance(second, OpenAIChatModel)


def test_anthropic_is_built_when_selected_and_allowed(kb: sa.Engine, canary: str) -> None:
    save_settings(
        kb,
        ProviderSettings(
            provider=Provider.ANTHROPIC, model="m", allow_external=True, api_key_env="K"
        ),
    )
    assert isinstance(build_model(kb, environ={"K": canary}), AnthropicModel)


def test_an_external_provider_is_refused_without_opt_in(kb: sa.Engine, canary: str) -> None:
    save_settings(kb, ProviderSettings(provider=Provider.ANTHROPIC, model="m", api_key_env="K"))
    with pytest.raises(ExternalProviderDisabledError, match="external"):
        build_model(kb, environ={"K": canary})  # refused BEFORE any client is constructed


def test_a_missing_api_key_env_is_an_error_not_a_fallback_to_ollama(kb: sa.Engine) -> None:
    save_settings(
        kb, ProviderSettings(provider=Provider.OPENAI, model="m", allow_external=True)
    )  # api_key_env left unset
    with pytest.raises(MissingApiKeyError):
        build_model(kb, environ={})


def test_an_unset_environment_variable_is_an_error_not_a_fallback_to_ollama(kb: sa.Engine) -> None:
    save_settings(
        kb,
        ProviderSettings(
            provider=Provider.OPENAI, model="m", allow_external=True, api_key_env="MISSING"
        ),
    )
    with pytest.raises(MissingApiKeyError, match="MISSING"):
        build_model(kb, environ={})


def test_ollama_never_needs_a_key_even_with_allow_external_off(kb: sa.Engine) -> None:
    save_settings(kb, ProviderSettings(provider=Provider.OLLAMA, model="m"))
    build_model(kb, environ={})  # must not raise


def test_a_custom_base_url_gets_the_v1_suffix_for_the_openai_compatible_endpoint(
    kb: sa.Engine,
) -> None:
    save_settings(
        kb, ProviderSettings(provider=Provider.OLLAMA, model="m", base_url="http://box:1234/")
    )
    model = build_model(kb, environ={})
    assert isinstance(model, OllamaModel)
    # A trailing slash on the stored host must not produce //v1.
    assert model.base_url == "http://box:1234/v1/"


def test_the_stored_base_url_stays_the_bare_host_not_the_v1_endpoint(kb: sa.Engine) -> None:
    """Embeddings (B2) call `{base_url}/api/embed`; only build_model appends /v1."""
    save_settings(
        kb, ProviderSettings(provider=Provider.OLLAMA, model="m", base_url="http://box:1234")
    )
    with kb.connect() as conn:
        row = conn.execute(sa.select(schema.app_setting)).one()
    assert row.base_url == "http://box:1234"
