"""Process configuration: defaults, environment overrides, and the loopback rule."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from cvforge.config import Settings


def test_defaults_are_local_only() -> None:
    settings = Settings()
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.data_dir == Path("data")
    assert settings.frontend_dist == Path("frontend/dist")


def test_environment_overrides_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CVFORGE_PORT", "9100")
    assert Settings().port == 9100


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", ""])  # noqa: S104
def test_non_loopback_host_is_rejected(host: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """NFR-02: the tool must never listen on an address reachable off the host."""
    monkeypatch.setenv("CVFORGE_HOST", host)
    with pytest.raises(ValidationError, match="loopback"):
        Settings()


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_hosts_are_accepted(host: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CVFORGE_HOST", host)
    assert Settings().host == host
