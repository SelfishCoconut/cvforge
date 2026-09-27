"""Application factory: one process serving the JSON API and the built SPA (ADR-0002)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import cvforge
from cvforge.api.errors import install_error_handlers
from cvforge.api.health import router as health_router
from cvforge.api.knowledge import router as knowledge_router
from cvforge.api.proposals import router as proposals_router
from cvforge.config import Settings
from cvforge.kb.migrate import open_database


def create_app(settings: Settings | None = None, *, engine: sa.Engine | None = None) -> FastAPI:
    """Build the CVForge application.

    The JSON API is mounted under `/api`. The built SPA is mounted at `/` only
    when it has been built — without it the API still works and `/` returns 404.

    The knowledge base is opened when the app starts, not when it is built: the
    lifespan opens `settings.database_path` and migrates it to head (backing it
    up first). Pass `engine` to use an already-open database instead, as the
    tests and the offline demos do.

    Args:
        settings: Process configuration. A default `Settings()` is read from the
            environment when omitted.
        engine: An open knowledge-base engine; the app does not dispose it.

    Returns:
        The configured application.
    """
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = engine is None
        app.state.engine = engine or open_database(settings.database_path, settings.backup_dir)
        yield
        if owned:
            app.state.engine.dispose()

    app = FastAPI(title="CVForge", version=cvforge.__version__, lifespan=lifespan)
    app.state.settings = settings
    install_error_handlers(app)
    app.include_router(health_router, prefix="/api")
    app.include_router(knowledge_router, prefix="/api")
    app.include_router(proposals_router, prefix="/api")
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
