"""Map write-path refusals to HTTP responses, and give routes the database."""

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
    UnsupportedOperationError,
)

_STATUS: dict[type[ApplyError], int] = {
    NotFoundError: 404,
    ProposalNotOpenError: 409,
    OperationsPendingError: 409,
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
    return JSONResponse(
        status_code=409,
        content={"detail": f"the database rejected the change; nothing was written: {error}"},
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register the refusal-to-status mapping on `app`.

    Args:
        app: The application.
    """
    app.add_exception_handler(ApplyError, _apply_error)
    app.add_exception_handler(sa.exc.IntegrityError, _integrity_error)
