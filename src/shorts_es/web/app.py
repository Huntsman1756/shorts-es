"""FastAPI application factory. Thin read-only shell around the domain.

No regulatory or business logic lives in endpoints: every handler delegates
to the same parser/domain/repository code the CLI uses.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..config import Config
from ..exceptions import (
    AmbiguousIdentifierError,
    NoDataError,
    ShortsEsError,
)
from ..storage import db

_WEB_DIR = Path(__file__).parent
STATUS_FOR_CODE = {
    "NOT_FOUND": 404,
    "NO_DATA": 404,
    "MISSING_SNAPSHOT": 404,
    "AMBIGUOUS_IDENTIFIER": 409,
    "INSUFFICIENT_KNOWLEDGE_HISTORY": 422,
    "VERIFICATION_FAILED": 409,
    "SCHEMA_DRIFT": 409,
}


def get_config(request: Request) -> Config:
    return request.app.state.config


def get_conn(config: Config = Depends(get_config)) -> Iterator[sqlite3.Connection]:
    conn = db.open_db(config.db_path)
    try:
        yield conn
    finally:
        conn.close()


def create_app(config: Config) -> FastAPI:
    app = FastAPI(
        title="shorts-es",
        version=__version__,
        description="Reproducible access to CNMV public net short-position disclosures.",
    )
    app.state.config = config

    app.mount(
        "/static",
        StaticFiles(directory=_WEB_DIR / "static"),
        name="static",
    )
    app.state.templates = Jinja2Templates(directory=_WEB_DIR / "templates")

    @app.exception_handler(ShortsEsError)
    async def _shorts_error(request: Request, exc: ShortsEsError) -> JSONResponse:
        status = STATUS_FOR_CODE.get(exc.code, 500)
        payload = {"error": exc.code, "message": exc.message}
        if isinstance(exc, AmbiguousIdentifierError):
            payload["candidates"] = exc.candidates
        return JSONResponse(payload, status_code=status)

    from . import routes

    app.include_router(routes.api, prefix="/api/v1")
    app.include_router(routes.pages)
    return app


def dataset_or_404(conn: sqlite3.Connection) -> sqlite3.Row:
    from ..storage import repository as repo

    snap = repo.latest_snapshot(conn)
    if snap is None:
        raise NoDataError("no snapshots ingested yet")
    return snap


# Module-level ASGI app for `uvicorn shorts_es.web.app:app`. Data directory
# comes from SHORTS_ES_DATA_DIR or the platform default.
app = create_app(Config.resolve())
