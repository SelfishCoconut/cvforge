"""FR-39: `/api/settings` reads and changes the persisted provider settings."""

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from cvforge.kb.vocab import Provider
from cvforge.llm.provider import build_model


def test_no_configuration_returns_the_local_ollama_default(client: TestClient) -> None:
    body = client.get("/api/settings").json()
    assert body == {
        "settings": {
            "provider": "ollama",
            "model": "qwen3.6:27b",
            "base_url": "http://127.0.0.1:11434",
            "api_key_env": None,
            "allow_external": False,
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "similarity_threshold": 0.85,
        },
        "api_key_configured": False,
    }


def test_the_key_value_never_appears_in_any_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, canary: str
) -> None:
    monkeypatch.setenv("MY_KEY", canary)
    client.put(
        "/api/settings",
        json={
            "provider": "openai",
            "model": "m",
            "base_url": None,
            "api_key_env": "MY_KEY",
            "allow_external": True,
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "similarity_threshold": 0.85,
        },
    )
    for response in (
        client.get("/api/settings"),
        client.put("/api/settings", json=client.get("/api/settings").json()["settings"]),
    ):
        assert canary not in response.text
    assert client.get("/api/settings").json()["api_key_configured"] is True


def test_an_external_provider_without_opt_in_is_a_422(client: TestClient) -> None:
    response = client.put(
        "/api/settings",
        json={
            "provider": "anthropic",
            "model": "m",
            "base_url": None,
            "api_key_env": "K",
            "allow_external": False,
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "similarity_threshold": 0.85,
        },
    )
    assert response.status_code == 422
    assert "external" in response.json()["detail"]


def test_a_key_env_named_but_unset_reports_not_configured(client: TestClient) -> None:
    client.put(
        "/api/settings",
        json={
            "provider": "openai",
            "model": "m",
            "base_url": None,
            "api_key_env": "SOME_VAR_NOBODY_SET",
            "allow_external": True,
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "similarity_threshold": 0.85,
        },
    )
    assert client.get("/api/settings").json()["api_key_configured"] is False


def test_an_update_changes_the_provider_of_the_next_build_model_call(
    client: TestClient, kb: sa.Engine, canary: str
) -> None:
    client.put(
        "/api/settings",
        json={
            "provider": "anthropic",
            "model": "m",
            "base_url": None,
            "api_key_env": "K",
            "allow_external": True,
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "similarity_threshold": 0.85,
        },
    )
    model = build_model(kb, environ={"K": canary})
    assert model.system == "anthropic"


def test_put_replaces_the_whole_settings_row_not_a_partial_patch(client: TestClient) -> None:
    client.put(
        "/api/settings",
        json={
            "provider": "ollama",
            "model": "custom-model",
            "base_url": "http://127.0.0.1:11434",
            "api_key_env": None,
            "allow_external": False,
            "embedding_provider": "ollama",
            "embedding_model": "nomic-embed-text",
            "similarity_threshold": 0.5,
        },
    )
    settings = client.get("/api/settings").json()["settings"]
    assert (settings["model"], settings["similarity_threshold"]) == ("custom-model", 0.5)
    assert settings["provider"] == Provider.OLLAMA.value
