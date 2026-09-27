"""Process configuration, read from the environment with local-first defaults."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from cvforge.kb.db import DATABASE_FILE

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class Settings(BaseSettings):
    """CVForge process configuration.

    Every field is overridable by a `CVFORGE_`-prefixed environment variable or
    an entry in a local `.env` file.

    Attributes:
        host: Address uvicorn binds to. Must be loopback (NFR-02).
        port: TCP port uvicorn binds to.
        data_dir: Directory holding private data — the knowledge base, uploaded
            documents and the browser profile. Never committed.
        frontend_dist: Directory holding the built SPA. The SPA is only served
            when it contains an `index.html`.
        allowed_hosts: Host header values the API answers to (NFR-02, audit
            F6). Binding to loopback stops a remote attacker; it does not stop
            a hostile page already open in the user's own browser making the
            browser's DNS resolve an attacker's hostname to 127.0.0.1. Every
            loopback form is listed regardless of which one `host` binds,
            since a browser may reach the same bound socket through any of them.
    """

    model_config = SettingsConfigDict(env_prefix="CVFORGE_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = Path("data")
    frontend_dist: Path = Path("frontend/dist")
    allowed_hosts: tuple[str, ...] = ("127.0.0.1", "localhost", "[::1]")

    @property
    def database_path(self) -> Path:
        """The single knowledge-base file under `data_dir` (NFR-09)."""
        return self.data_dir / DATABASE_FILE

    @property
    def backup_dir(self) -> Path:
        """Where pre-migration copies of the database are written."""
        return self.data_dir / "backups"

    @field_validator("host")
    @classmethod
    def _reject_non_loopback(cls, value: str) -> str:
        """Reject any bind address reachable from outside this machine.

        Args:
            value: The configured host.

        Returns:
            The host, unchanged, when it is a loopback address.

        Raises:
            ValueError: If the host is not a loopback address (NFR-02).
        """
        if value not in LOOPBACK_HOSTS:
            raise ValueError(
                f"host must be a loopback address (one of {sorted(LOOPBACK_HOSTS)}), got {value!r}"
            )
        return value
