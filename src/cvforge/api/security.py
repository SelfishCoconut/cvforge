"""Local-only defenses a browser on this machine still needs (NFR-02, audit F6).

Binding to `127.0.0.1` stops a remote attacker; it does not stop a hostile page
already open in the user's own browser. Two checks close that gap:

- `refuse_foreign_host` rejects a request whose `Host` header does not name one
  of `settings.allowed_hosts`. Without it, DNS rebinding lets an attacker's page
  make the browser resolve the attacker's own hostname to `127.0.0.1` and reach
  the API anyway.
- `refuse_foreign_origin` rejects a state-changing request (`POST`, `PUT`,
  `PATCH`, `DELETE`) whose `Origin` names a host other than one of the same
  addresses. A `GET` is never blocked: every mutation this API exposes is one
  of those four methods, so a safe method carries no side effect to protect,
  and reading the response of a cross-origin request is already stopped by the
  browser's own CORS policy — this app sends no permissive CORS headers.

Both use the same bracket-aware host parsing. Starlette's own
`TrustedHostMiddleware` splits a `Host` header on the first `:`, which lands
inside the brackets of an IPv6 literal (`[::1]:8000` becomes `[`), so it is not
used here.
"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from starlette.responses import PlainTextResponse, Response

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CallNext = Callable[[Request], Awaitable[Response]]


def _host_from_header(value: str) -> str:
    """The bare host from a `Host:` header value, keeping IPv6 brackets (`[::1]:8000` → `[::1]`)."""
    value = value.strip()
    if value.startswith("["):
        return value[: value.index("]") + 1]
    return value.split(":", 1)[0]


def _bare(host: str) -> str:
    """Drop the brackets HTTP puts around an IPv6 literal (`[::1]` → `::1`)."""
    return host.strip("[]")


async def refuse_foreign_host(request: Request, call_next: CallNext) -> Response:
    """Refuse a request whose `Host` header does not name this app's own address.

    Args:
        request: The incoming request.
        call_next: The rest of the middleware chain.

    Returns:
        A 400 response if the host is not allowed; otherwise the chain's response.
    """
    allowed = request.app.state.settings.allowed_hosts
    host = _host_from_header(request.headers.get("host", ""))
    if host not in allowed:
        return PlainTextResponse("invalid host header", status_code=400)
    return await call_next(request)


async def refuse_foreign_origin(request: Request, call_next: CallNext) -> Response:
    """Refuse a state-changing request whose `Origin` names a host other than this app's own.

    Args:
        request: The incoming request.
        call_next: The rest of the middleware chain.

    Returns:
        A 403 response if an unsafe method carries a foreign `Origin`;
        otherwise the chain's response.
    """
    origin = request.headers.get("origin")
    if request.method in UNSAFE_METHODS and origin is not None:
        allowed = {_bare(host) for host in request.app.state.settings.allowed_hosts}
        if _bare(urlsplit(origin).hostname or "") not in allowed:
            return PlainTextResponse("cross-origin request refused", status_code=403)
    return await call_next(request)


def install_security_middleware(app: FastAPI) -> None:
    """Register both local-only defenses on `app` (NFR-02, audit F6).

    `app.state.settings` must already be set; both checks read
    `allowed_hosts` from it at request time, so a settings change would take
    effect immediately if it were ever runtime-changeable (it isn't yet).

    Args:
        app: The application.
    """
    # Registered in this order so the host check is outermost: the last
    # middleware added wraps every other one and runs first.
    app.middleware("http")(refuse_foreign_origin)
    app.middleware("http")(refuse_foreign_host)
