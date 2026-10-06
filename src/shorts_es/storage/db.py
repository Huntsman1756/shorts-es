"""SQLite connection management."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

SCHEMA_VERSION = "2"


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    sql = resources.files("shorts_es.storage").joinpath("schema.sql").read_text("utf-8")
    conn.executescript(sql)
    # v1 -> v2: snapshots gained physical_fingerprint (audit-only).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(snapshot)")}
    if "physical_fingerprint" not in cols:
        conn.execute("ALTER TABLE snapshot ADD COLUMN physical_fingerprint TEXT")
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()


def open_db(db_path: str | Path) -> sqlite3.Connection:
    conn = connect(db_path)
    migrate(conn)
    return conn
