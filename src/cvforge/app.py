"""Application factory: one process serving the JSON API and the built SPA (ADR-0002)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import cvforge
from cvforge.api.health import router as health_router
from cvforge.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the CVForge application.

    The JSON API is mounted under `/api`. The built SPA is mounted at `/` only
    when it has been built — without it the API still works and `/` returns 404.

    Args:
        settings: Process configuration. A default `Settings()` is read from the
            environment when omitted.

    Returns:
        The configured application.
    """
    settings = settings or Settings()
    app = FastAPI(title="CVForge", version=cvforge.__version__)
    app.state.settings = settings
    app.include_router(health_router, prefix="/api")
    _mount_spa(app, settings.frontend_dist)
    return app


def _mount_spa(app: FastAPI, dist: Path) -> bool:
    """Mount the built SPA at `/`, if it has been built.

    Mounting happens after the API routes are registered, so `/api/...` always
    wins over the catch-all static mount.

    Args:
        app: The application to mount onto.
        dist: Directory expected to contain the built `index.html`.

    Returns:
        True when the SPA was mounted, False when there is nothing built to serve.
    """
    if not (dist / "index.html").is_file():
        return False
    app.mount("/", StaticFiles(directory=dist, html=True), name="spa")
    return True
