"""Liveness endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

import cvforge

router = APIRouter(tags=["system"])


class Health(BaseModel):
    """Liveness payload.

    Attributes:
        status: Always `ok` when the process is serving.
        version: The running `cvforge` package version.
    """

    status: str
    version: str


@router.get("/health")
def health() -> Health:
    """Report that the process is serving, and which version is running.

    Returns:
        The liveness payload.
    """
    return Health(status="ok", version=cvforge.__version__)
