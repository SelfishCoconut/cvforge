"""FR-39: provider settings persist in the database and seed from the environment once."""

import pytest
import sqlalchemy as sa

from cvforge.kb import schema
from cvforge.kb.vocab import Provider
from cvforge.llm.settings_store import ProviderSettings, load_settings, save_settings


def test_first_run_seeds_from_env_exactly_once(kb: sa.Engine) -> None:
    env = {
        "CVFORGE_LLM_PROVIDER": "openai",
        "CVFORGE_LLM_MODEL": "gpt-x",
        "CVFORGE_LLM_ALLOW_EXTERNAL": "true",
    }
    assert load_settings(kb, environ=env).model == "gpt-x"
    # The row exists now; a later call's environ is ignored — the database is authoritative.
    assert load_settings(kb, environ={"CVFORGE_LLM_MODEL": "changed"}).model == "gpt-x"


def test_no_configuration_defaults_to_local_ollama(kb: sa.Engine) -> None:
    settings = load_settings(kb, environ={})
    assert (settings.provider, settings.base_url) == (Provider.OLLAMA, "http://127.0.0.1:11434")
    assert settings.allow_external is False


def test_every_seedable_field_is_read_from_its_env_var(kb: sa.Engine) -> None:
    env = {
        "CVFORGE_LLM_PROVIDER": "anthropic",
        "CVFORGE_LLM_MODEL": "claude-x",
        "CVFORGE_LLM_BASE_URL": "https://example.test",
        "CVFORGE_LLM_API_KEY_ENV": "MY_KEY",
        "CVFORGE_LLM_ALLOW_EXTERNAL": "true",
        "CVFORGE_LLM_EMBEDDING_PROVIDER": "ollama",
        "CVFORGE_LLM_EMBEDDING_MODEL": "some-embedder",
        "CVFORGE_LLM_SIMILARITY_THRESHOLD": "0.5",
    }
    settings = load_settings(kb, environ=env)
    assert settings == ProviderSettings(
        provider=Provider.ANTHROPIC,
        model="claude-x",
        base_url="https://example.test",
        api_key_env="MY_KEY",
        allow_external=True,
        embedding_provider="ollama",
        embedding_model="some-embedder",
        similarity_threshold=0.5,
    )


def test_an_unset_env_var_leaves_the_field_at_its_default(kb: sa.Engine) -> None:
    settings = load_settings(kb, environ={"CVFORGE_LLM_MODEL": "only-this-one"})
    assert (settings.model, settings.provider) == ("only-this-one", Provider.OLLAMA)


def test_a_malformed_provider_env_var_on_first_run_raises_rather_than_silently_defaulting(
    kb: sa.Engine,
) -> None:
    with pytest.raises(ValueError, match="not-a-real-provider"):
        load_settings(kb, environ={"CVFORGE_LLM_PROVIDER": "not-a-real-provider"})


def test_a_malformed_similarity_threshold_env_var_on_first_run_raises(kb: sa.Engine) -> None:
    with pytest.raises(ValueError, match="not-a-float"):
        load_settings(kb, environ={"CVFORGE_LLM_SIMILARITY_THRESHOLD": "not-a-float"})


def test_saving_replaces_the_stored_settings(kb: sa.Engine) -> None:
    load_settings(kb, environ={})  # seed the row
    save_settings(kb, ProviderSettings(provider=Provider.OLLAMA, model="qwen-new"))
    assert load_settings(kb, environ={"CVFORGE_LLM_MODEL": "ignored"}).model == "qwen-new"


def test_an_unsupported_provider_name_is_rejected_by_the_database(kb: sa.Engine) -> None:
    """A value that slips past Pydantic still cannot reach a row (CHECK constraint)."""
    now = sa.func.current_timestamp()
    with pytest.raises(sa.exc.IntegrityError, match="ck_app_setting_provider"), kb.begin() as conn:
        conn.execute(
            sa.insert(schema.app_setting).values(
                id=1,
                provider="grok",
                model="m",
                allow_external=False,
                embedding_provider="ollama",
                embedding_model="nomic-embed-text",
                similarity_threshold=0.85,
                updated_at=now,
            )
        )


def test_the_settings_row_never_holds_a_resolved_secret_value(
    kb: sa.Engine, canary: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real env var holds the "secret"; only its NAME may ever reach the row."""
    monkeypatch.setenv("MY_KEY", canary)
    save_settings(
        kb,
        ProviderSettings(
            provider=Provider.OPENAI, model="m", api_key_env="MY_KEY", allow_external=True
        ),
    )
    with kb.connect() as conn:
        row = conn.execute(sa.select(schema.app_setting)).one()
    assert canary not in str(row)
    assert row.api_key_env == "MY_KEY"
