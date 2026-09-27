"""NFR-02: the socket-level guarantee that the app is reachable from nowhere but loopback.

The `host` field validation is held by `tests/unit/test_config.py`, and the
Host/Origin middleware logic by `tests/unit/test_security_middleware.py` — both
run in-process, no real socket. This file is the one test that needs a real,
non-loopback connection attempt against a genuinely running server, which is
what makes it `integration` rather than `unit`.
"""

import socket
import threading
import time
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
import uvicorn

from cvforge.app import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def running_app(kb: sa.Engine) -> Iterator[int]:
    """A real uvicorn server bound to 127.0.0.1 on an ephemeral port; yields that port."""
    server = uvicorn.Server(
        uvicorn.Config(create_app(engine=kb), host="127.0.0.1", port=0, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started:
        if time.monotonic() > deadline:
            raise TimeoutError("uvicorn did not report started within 5s")
        time.sleep(0.01)
    bound_host, port = server.servers[0].sockets[0].getsockname()[:2]
    assert bound_host == "127.0.0.1", f"bound to {bound_host}, not 127.0.0.1 — NFR-02"
    try:
        yield port
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_a_request_from_a_non_local_origin_cannot_reach_the_api(
    running_app: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The socket-level guarantee behind NFR-02: bound to 127.0.0.1, reachable from nowhere else.

    This is the one test in the suite that needs a real, non-loopback socket
    attempt, so it explicitly lifts the suite-wide network guard
    (`conftest._no_live_traffic`) for its own duration.
    """
    monkeypatch.undo()  # this test's whole point is a real non-loopback connection attempt

    # Route discovery, not traffic: a UDP "connect" only asks the kernel which local
    # address it would use, and sends nothing (confirmed empirically: 0.0s, no hang,
    # unlike an actual off-host connection attempt in this sandbox).
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        local_ip = probe.getsockname()[0]
    except OSError:
        pytest.skip("this environment has no configured network route to discover a local IP")
    finally:
        probe.close()
    if local_ip == "127.0.0.1":
        pytest.skip("this environment's only route is loopback; nothing to test against")

    with pytest.raises(OSError):
        socket.create_connection((local_ip, running_app), timeout=3)
