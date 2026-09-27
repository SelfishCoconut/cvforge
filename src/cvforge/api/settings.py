"""Read and change the persisted LLM provider settings (FR-39).

There is no endpoint, and no response field, that ever carries an API key's
value — only `api_key_env`, the name of the environment variable holding it.
"""

import os
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cvforge.api.errors import engine
from cvforge.llm.provider import EXTERNAL
from cvforge.llm.settings_store import ProviderSettings, load_settings, save_settings

router = APIRouter(tags=["settings"])
Engine = Annotated[sa.Engine, Depends(engine)]


class SettingsView(BaseModel):
    """The persisted settings, plus whether a usable key is configured — never the key itself.

    Attributes:
        settings: The persisted provider settings.
        api_key_configured: True when `settings.api_key_env` names a real,
            currently-set environment variable. False both when no name is
            set and when the named variable is unset — a caller who only
            wants "is a key needed and missing" reads this one field either way.
    """

    settings: ProviderSettings
    api_key_configured: bool


def _refuse_disabled_external(body: ProviderSettings) -> None:
    if body.provider in EXTERNAL and not body.allow_external:
        raise HTTPException(
            422, f"{body.provider} is an external provider; set allow_external to use it (NFR-01)"
        )


def _view(settings: ProviderSettings) -> SettingsView:
    configured = bool(settings.api_key_env) and bool(os.environ.get(settings.api_key_env or ""))
    return SettingsView(settings=settings, api_key_configured=configured)


@router.get("/settings")
def get_settings(db: Engine) -> SettingsView:
    """Return the currently persisted provider settings.

    Args:
        db: The knowledge-base engine.

    Returns:
        The settings.
    """
    return _view(load_settings(db))


@router.put("/settings")
def put_settings(db: Engine, body: ProviderSettings) -> SettingsView:
    """Replace the persisted provider settings.

    Args:
        db: The knowledge-base engine.
        body: The full replacement settings.

    Returns:
        The settings, as persisted.

    Raises:
        HTTPException: 422 if `body` selects Anthropic or OpenAI without
            `allow_external` (NFR-01).
    """
    _refuse_disabled_external(body)
    return _view(save_settings(db, body))
