"""Map write-path refusals to HTTP responses, and give routes the database.

The contract every route shares:

| Refusal | Status |
|---|---|
| `NotFoundError` | 404 |
| `ProposalNotOpenError`, `OperationsPendingError`, `StaleClassificationError` | 409 |
| `InvalidEditError`, `UnsupportedOperationError` | 422 |
| any other `ApplyError` | 400 |
| `sqlalchemy.exc.IntegrityError` (the database rejected the change) | 409 |
| `sqlalchemy.exc.OperationalError`, database locked past the busy timeout | 503, `Retry-After: 1` |
| any other `sqlalchemy.exc.OperationalError` | 500 |

The body is always `{"detail": "<message>"}`, and a refusal leaves the database
as it was.
"""

from collections.abc import Iterator

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from cvforge.kb.apply import (
    ApplyError,
    InvalidEditError,
    NotFoundError,
    OperationsPendingError,
    ProposalNotOpenError,
    StaleClassificationError,
    UnsupportedOperationError,
)

_STATUS: dict[type[ApplyError], int] = {
    NotFoundError: 404,
    ProposalNotOpenError: 409,
    OperationsPendingError: 409,
    StaleClassificationError: 409,
    InvalidEditError: 422,
    UnsupportedOperationError: 422,
}


def engine(request: Request) -> sa.Engine:
    """FastAPI dependency: the knowledge-base engine opened by the app lifespan.

    Args:
        request: The incoming request.

    Returns:
        The engine.
    """
    result: sa.Engine = request.app.state.engine
    return result


def connection(request: Request) -> Iterator[sa.Connection]:
    """FastAPI dependency: a read connection, closed after the request.

    Args:
        request: The incoming request.

    Yields:
        An open connection.
    """
    with engine(request).connect() as conn:
        yield conn


async def _apply_error(_request: Request, error: Exception) -> JSONResponse:
    status = next((code for kind, code in _STATUS.items() if isinstance(error, kind)), 400)
    return JSONResponse(status_code=status, content={"detail": str(error)})


async def _integrity_error(_request: Request, error: Exception) -> JSONResponse:
    # `orig` is the driver's message ("UNIQUE constraint failed: ..."). The wrapper's
    # own text also carries the SQL statement and its bound parameters.
    reason = getattr(error, "orig", error)
    return JSONResponse(
        status_code=409,
        content={"detail": f"the database rejected the change; nothing was written: {reason}"},
    )


async def _operational_error(_request: Request, error: Exception) -> JSONResponse:
    reason = str(getattr(error, "orig", error))
    if "locked" in reason:
        # Review and commit take SQLite's write lock before they read (`apply._write_transaction`),
        # so a request that waits longer than the busy timeout never began: nothing was written.
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "1"},
            content={"detail": "the knowledge base is busy; nothing was written, try again"},
        )
    return JSONResponse(status_code=500, content={"detail": "the database failed"})


def install_error_handlers(app: FastAPI) -> None:
    """Register the refusal-to-status mapping on `app`.

    Args:
        app: The application.
    """
    app.add_exception_handler(ApplyError, _apply_error)
    app.add_exception_handler(sa.exc.IntegrityError, _integrity_error)
    app.add_exception_handler(sa.exc.OperationalError, _operational_error)
