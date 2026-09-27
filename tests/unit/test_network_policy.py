"""NFR-01/NFR-08: no test may reach a non-local host, and no test may call a live model.

The guard these tests hold is the autouse `_no_live_traffic` fixture in
`tests/conftest.py`. It exists so a future test cannot silently grow a live
dependency: this file proves the guard is armed, not that any test currently
needs it.
"""

import socket

import pytest
from pydantic_ai import models


def test_a_non_loopback_connection_is_refused() -> None:
    with (
        socket.socket() as sock,
        pytest.raises(OSError, match="non-local network access is disabled"),
    ):
        sock.connect(("93.184.216.34", 80))


def test_a_loopback_connection_is_allowed() -> None:
    """The guard must not break ordinary local sockets (the TestClient, the DB)."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.socket()
    client.connect(server.getsockname())
    client.close()
    server.close()


def test_a_real_model_request_is_refused() -> None:
    assert models.ALLOW_MODEL_REQUESTS is False
