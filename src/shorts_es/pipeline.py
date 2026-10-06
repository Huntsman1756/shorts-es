"""Sync pipeline: source -> snapshot -> inspect -> parse -> ledger.

Ordering is strict and observable. A snapshot's raw bytes are persisted
before parsing; schema drift still leaves the raw snapshot and a status row
so the event is auditable.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass

from . import constants
from .config import Config
from .exceptions import SchemaDriftError, ShortsEsError
from .parser.workbook import parse_workbook
from .source import fetch as source_fetch
from .source.inspect import inspect_workbook
from .source.schema import validate_schema
from .source.snapshot import append_manifest, store_snapshot
from .storage import db
from .storage import repository as repo

log = logging.getLogger("shorts_es")


@dataclass(frozen=True)
class SyncResult:
    sha256: str
    status: str  # NO_CHANGE | CREATED | SCHEMA_DRIFT | PARSE_ERROR
    retrieved_at: str
    new_disclosures: int
    total_rows: int
    publication_date: str | None


def _fetch(config: Config, file: str | None, url: str | None):
    if file:
        return source_fetch.fetch_local(file, source_url=url or constants.SOURCE_URL)
    return source_fetch.fetch_source(url or constants.SOURCE_URL)


def sync(config: Config, file: str | None = None, url: str | None = None) -> SyncResult:
    log.info("sync_started")
    fetched = _fetch(config, file, url)
    stored = store_snapshot(config, fetched)
    log.info("source_downloaded sha256=%s bytes=%d", stored.sha256, len(fetched.content))

    conn = db.open_db(config.db_path)
    try:
        info = inspect_workbook(fetched.content)
        status = "parsed"
        parsed = None
        err: ShortsEsError | None = None
        try:
            validate_schema(info)
            log.info("schema_valid fingerprint=%s", info.fingerprint)
            parsed = parse_workbook(fetched.content)
            log.info("parse_complete rows=%d", len(parsed.rows))
        except SchemaDriftError as exc:
            status = "schema_drift"
            err = exc
            log.error("schema_drift %s", exc)
        except ShortsEsError as exc:
            status = "parse_error"
            err = exc
            log.error("parse_error %s", exc)

        outcome = repo.ingest_snapshot(conn, stored, info, parsed, status)
        if outcome == "exists":
            return SyncResult(
                sha256=stored.sha256,
                status="NO_CHANGE",
                retrieved_at=stored.retrieved_at.isoformat(),
                new_disclosures=0,
                total_rows=len(parsed.rows) if parsed else 0,
                publication_date=parsed.publication_date.isoformat()
                if parsed and parsed.publication_date
                else None,
            )

        append_manifest(
            config,
            {
                "retrieved_at": stored.retrieved_at.isoformat(),
                "sha256": stored.sha256,
                "source_url": fetched.source_url,
                "size": fetched.content_length,
                "etag": fetched.etag,
                "last_modified": fetched.last_modified,
                "publication_date": parsed.publication_date.isoformat()
                if parsed and parsed.publication_date
                else None,
                "parser_version": constants.PARSER_VERSION,
                "schema_fingerprint": info.fingerprint,
                "status": status,
                "rows": {s.name: s.nrows for s in info.sheets},
            },
        )

        if err is not None:
            raise err

        new_disc = sum(1 for _ in repo.disclosure_ids_since_snapshot(conn, stored.sha256))
        return SyncResult(
            sha256=stored.sha256,
            status="CREATED" if outcome == "created" else "UPDATED",
            retrieved_at=stored.retrieved_at.isoformat(),
            new_disclosures=new_disc,
            total_rows=len(parsed.rows) if parsed else 0,
            publication_date=parsed.publication_date.isoformat()
            if parsed and parsed.publication_date
            else None,
        )
    finally:
        conn.close()


def connect(config: Config) -> sqlite3.Connection:
    """Read path helper: open (and lazily migrate) the ledger."""
    return db.open_db(config.db_path)
