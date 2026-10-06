"""Storage repository: ingestion and read queries.

Write path is idempotent: re-ingesting the same snapshot records no
duplicates. Disclosures keep ``first_observed_at`` (knowledge time) from the
first snapshot that contained them.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from ..parser.models import ParsedWorkbook
from ..source.inspect import WorkbookInfo
from ..source.snapshot import StoredSnapshot


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


# ---------------------------------------------------------------- ingestion


def ingest_snapshot(
    conn: sqlite3.Connection,
    stored: StoredSnapshot,
    info: WorkbookInfo,
    parsed: ParsedWorkbook | None,
    status: str,
) -> str:
    """Persist a snapshot and (when parsed) its disclosures.

    Returns ``"created"``, ``"updated"`` (a previously failed snapshot is
    re-ingested, e.g. schema drift fixed by a parser update) or ``"exists"``
    (already parsed; nothing to do). All writes are idempotent.
    """
    existing = conn.execute(
        "SELECT status, parser_version FROM snapshot WHERE snapshot_sha256 = ?",
        (stored.sha256,),
    ).fetchone()
    if (
        existing is not None
        and existing["status"] == "parsed"
        and status == "parsed"
        and existing["parser_version"] == _parser_version()
    ):
        return "exists"

    f = stored.fetch
    publication_date = (
        parsed.publication_date.isoformat() if parsed and parsed.publication_date else None
    )
    with conn:
        if existing is None:
            conn.execute(
                """INSERT INTO snapshot (
                       snapshot_sha256, retrieved_at, source_url, http_status,
                       content_type, content_length, etag, last_modified,
                       publication_date, parser_version, schema_fingerprint,
                       physical_fingerprint, status, raw_path)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stored.sha256,
                    _iso(stored.retrieved_at),
                    f.source_url,
                    f.http_status,
                    f.content_type,
                    f.content_length,
                    f.etag,
                    f.last_modified,
                    publication_date,
                    _parser_version(),
                    info.fingerprint,
                    info.physical_fingerprint,
                    status,
                    str(stored.raw_path),
                ),
            )
            for s in info.sheets:
                conn.execute(
                    """INSERT INTO snapshot_sheet
                       (snapshot_sha256, sheet_name, sheet_order, row_count, col_count)
                       VALUES (?,?,?,?,?)""",
                    (stored.sha256, s.name, s.order, s.nrows, s.ncols),
                )
        else:
            conn.execute(
                """UPDATE snapshot SET retrieved_at = ?, source_url = ?,
                       http_status = ?, content_type = ?, content_length = ?,
                       etag = ?, last_modified = ?, publication_date = ?,
                       parser_version = ?, schema_fingerprint = ?,
                       physical_fingerprint = ?, status = ?
                   WHERE snapshot_sha256 = ?""",
                (
                    _iso(stored.retrieved_at),
                    f.source_url,
                    f.http_status,
                    f.content_type,
                    f.content_length,
                    f.etag,
                    f.last_modified,
                    publication_date,
                    _parser_version(),
                    info.fingerprint,
                    info.physical_fingerprint,
                    status,
                    stored.sha256,
                ),
            )
        if parsed is not None:
            _ingest_rows(conn, stored, parsed)
        if status == "parsed":
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('latest_snapshot', ?)",
                (stored.sha256,),
            )
    return "created" if existing is None else "updated"


def _parser_version() -> str:
    from .. import constants

    return constants.PARSER_VERSION


def _ingest_rows(conn: sqlite3.Connection, stored: StoredSnapshot, parsed: ParsedWorkbook) -> None:
    seen_at = _iso(stored.retrieved_at)
    for row in parsed.rows:
        d = row.disclosure
        conn.execute(
            """INSERT OR IGNORE INTO disclosure (
                   disclosure_id, lei, isin, issuer_name, holder_name,
                   position_date, position_pct, canonical_json,
                   first_observed_at, first_snapshot_sha256)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                d.disclosure_id,
                d.lei,
                d.isin,
                d.issuer_name,
                d.holder_name,
                d.position_date.isoformat(),
                d.pct_str,
                d.canonical_json(),
                seen_at,
                stored.sha256,
            ),
        )
        conn.execute(
            """INSERT OR IGNORE INTO snapshot_disclosure
               (snapshot_sha256, disclosure_id, sheet_name, row_number)
               VALUES (?,?,?,?)""",
            (stored.sha256, d.disclosure_id, row.sheet_name, row.row_number),
        )


def record_verification(
    conn: sqlite3.Connection,
    snapshot_sha256: str,
    result: str,
    counts: dict,
    details: dict,
) -> None:
    with conn:
        conn.execute(
            """INSERT INTO verification
               (snapshot_sha256, verified_at, result, pairs_checked,
                matched, missing, unexpected, conflicts, details_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                snapshot_sha256,
                _iso(datetime.now(UTC)),
                result,
                counts["pairs_checked"],
                counts["matched"],
                counts["missing"],
                counts["unexpected"],
                counts["conflicts"],
                json.dumps(details, ensure_ascii=False, sort_keys=True),
            ),
        )


# ------------------------------------------------------------------ queries


def list_snapshots(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM snapshot ORDER BY retrieved_at").fetchall()


def get_snapshot(conn: sqlite3.Connection, sha256: str) -> sqlite3.Row | None:
    row = conn.execute("SELECT * FROM snapshot WHERE snapshot_sha256 = ?", (sha256,)).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM snapshot WHERE snapshot_sha256 LIKE ? LIMIT 2",
            (sha256 + "%",),
        ).fetchall()
        if len(row) == 1:
            return row[0]
        return None
    return row


def latest_snapshot(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM snapshot WHERE status = 'parsed' " "ORDER BY retrieved_at DESC LIMIT 1"
    ).fetchone()


def latest_snapshot_before(conn: sqlite3.Connection, retrieved_at: str) -> sqlite3.Row | None:
    """Latest parsed snapshot observed at or before a knowledge cutoff."""
    return conn.execute(
        "SELECT * FROM snapshot WHERE status = 'parsed' AND retrieved_at <= ? "
        "ORDER BY retrieved_at DESC LIMIT 1",
        (retrieved_at,),
    ).fetchone()


def snapshot_sheets(conn: sqlite3.Connection, sha256: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM snapshot_sheet WHERE snapshot_sha256 = ? ORDER BY sheet_order",
        (sha256,),
    ).fetchall()


def snapshot_disclosure_ids(
    conn: sqlite3.Connection, sha256: str, sheet: str | None = None
) -> set[str]:
    if sheet:
        rows = conn.execute(
            "SELECT DISTINCT disclosure_id FROM snapshot_disclosure "
            "WHERE snapshot_sha256 = ? AND sheet_name = ?",
            (sha256, sheet),
        )
    else:
        rows = conn.execute(
            "SELECT DISTINCT disclosure_id FROM snapshot_disclosure " "WHERE snapshot_sha256 = ?",
            (sha256,),
        )
    return {r[0] for r in rows}


def disclosures_for_snapshot(
    conn: sqlite3.Connection, sha256: str, sheet: str | None = None
) -> list[sqlite3.Row]:
    sql = """SELECT DISTINCT d.* FROM disclosure d
             JOIN snapshot_disclosure sd ON sd.disclosure_id = d.disclosure_id
             WHERE sd.snapshot_sha256 = ?"""
    args: list = [sha256]
    if sheet:
        sql += " AND sd.sheet_name = ?"
        args.append(sheet)
    return conn.execute(sql, args).fetchall()


def get_disclosure(conn: sqlite3.Connection, disclosure_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM disclosure WHERE disclosure_id = ?", (disclosure_id,)
    ).fetchone()


def disclosure_provenance(conn: sqlite3.Connection, disclosure_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT sd.*, s.retrieved_at, s.source_url, s.parser_version,
                  s.schema_fingerprint
           FROM snapshot_disclosure sd
           JOIN snapshot s ON s.snapshot_sha256 = sd.snapshot_sha256
           WHERE sd.disclosure_id = ?
           ORDER BY s.retrieved_at, sd.sheet_name, sd.row_number""",
        (disclosure_id,),
    ).fetchall()


def disclosures_for_issuer(
    conn: sqlite3.Connection, isin: str, known_at: str | None = None
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM disclosure WHERE isin = ?"
    args: list = [isin]
    if known_at:
        sql += " AND first_observed_at <= ?"
        args.append(known_at)
    sql += " ORDER BY holder_name, position_date DESC"
    return conn.execute(sql, args).fetchall()


def disclosures_for_holder(
    conn: sqlite3.Connection, holder_name: str, known_at: str | None = None
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM disclosure WHERE holder_name = ?"
    args: list = [holder_name]
    if known_at:
        sql += " AND first_observed_at <= ?"
        args.append(known_at)
    sql += " ORDER BY isin, position_date DESC"
    return conn.execute(sql, args).fetchall()


def all_issuers(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT isin, lei, issuer_name, COUNT(*) AS n,
                  MIN(position_date) AS first_date, MAX(position_date) AS last_date
           FROM disclosure GROUP BY isin ORDER BY issuer_name"""
    ).fetchall()


def all_holders(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT holder_name, COUNT(*) AS n, COUNT(DISTINCT isin) AS issuers
           FROM disclosure GROUP BY holder_name ORDER BY holder_name"""
    ).fetchall()


def issuer_names_matching(conn: sqlite3.Connection, text: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT DISTINCT isin, lei, issuer_name FROM disclosure
           WHERE issuer_name LIKE ? COLLATE NOCASE ORDER BY issuer_name""",
        (f"%{text}%",),
    ).fetchall()


def holder_names_matching(conn: sqlite3.Connection, text: str) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT holder_name FROM disclosure "
            "WHERE holder_name LIKE ? COLLATE NOCASE ORDER BY holder_name",
            (f"%{text}%",),
        )
    ]


def disclosures_first_observed_since(conn: sqlite3.Connection, since_iso: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM disclosure WHERE first_observed_at >= ? "
        "ORDER BY first_observed_at, isin, holder_name",
        (since_iso,),
    ).fetchall()


def dataset_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """SELECT COUNT(*) AS disclosures,
                  COUNT(DISTINCT isin) AS issuers,
                  COUNT(DISTINCT lei) AS leis,
                  COUNT(DISTINCT holder_name) AS holders,
                  COUNT(DISTINCT lei || '|' || isin || '|' || holder_name) AS pairs,
                  MIN(position_date) AS earliest, MAX(position_date) AS latest
           FROM disclosure"""
    ).fetchone()
    snaps = conn.execute("SELECT COUNT(*) FROM snapshot").fetchone()[0]
    return {**dict(row), "snapshots": snaps}


def latest_verification(conn: sqlite3.Connection, sha256: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM verification WHERE snapshot_sha256 = ? " "ORDER BY id DESC LIMIT 1",
        (sha256,),
    ).fetchone()


def resolve_pair_disclosures(
    conn: sqlite3.Connection,
    lei: str,
    isin: str,
    holder: str,
    known_at: str | None = None,
) -> list[sqlite3.Row]:
    sql = """SELECT * FROM disclosure
             WHERE lei = ? AND isin = ? AND holder_name = ?"""
    args: list = [lei, isin, holder]
    if known_at:
        sql += " AND first_observed_at <= ?"
        args.append(known_at)
    sql += " ORDER BY position_date"
    return conn.execute(sql, args).fetchall()


def isin_exists(conn: sqlite3.Connection, isin: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM disclosure WHERE isin = ? LIMIT 1", (isin,)).fetchone()
        is not None
    )


def lei_exists(conn: sqlite3.Connection, lei: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM disclosure WHERE lei = ? LIMIT 1", (lei,)).fetchone()
        is not None
    )


def isins_for_lei(conn: sqlite3.Connection, lei: str) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT isin FROM disclosure WHERE lei = ? ORDER BY isin", (lei,)
        )
    ]


def current_sheet_pairs(conn: sqlite3.Connection, sha256: str) -> list[sqlite3.Row]:
    """Disclosures present in the Current sheet of a snapshot."""
    from .. import constants

    return conn.execute(
        """SELECT DISTINCT d.* FROM disclosure d
           JOIN snapshot_disclosure sd ON sd.disclosure_id = d.disclosure_id
           WHERE sd.snapshot_sha256 = ? AND sd.sheet_name = ?""",
        (sha256, constants.SHEET_CURRENT),
    ).fetchall()


def _canonical_pct_total(pcts: Iterable[str]) -> Decimal:
    return sum(Decimal(p) for p in pcts)


def _pct_str(total: Decimal) -> str:
    if total == total.to_integral():
        return str(total.quantize(Decimal(1)))
    return format(total.normalize(), "f")


def issuer_current_ranking(conn: sqlite3.Connection, snapshot_sha256: str) -> list[dict]:
    """Per-ISIN aggregation over the snapshot's Current sheet only.

    disclosed_total = exact Decimal sum of published individual positions
    (NOT total short interest). funds = number of holder pairs in Current.
    """
    from .. import constants

    rows = conn.execute(
        """SELECT d.isin, d.lei, d.issuer_name, d.holder_name,
                  d.position_pct, d.position_date
           FROM disclosure d
           JOIN snapshot_disclosure sd ON sd.disclosure_id = d.disclosure_id
           WHERE sd.snapshot_sha256 = ? AND sd.sheet_name = ?""",
        (snapshot_sha256, constants.SHEET_CURRENT),
    ).fetchall()
    by_isin: dict[str, dict] = {}
    for r in rows:
        e = by_isin.setdefault(
            r["isin"],
            {
                "isin": r["isin"],
                "lei": r["lei"],
                "issuer_name": r["issuer_name"],
                "funds": 0,
                "pcts": [],
                "last_position_date": "",
            },
        )
        e["funds"] += 1
        e["pcts"].append(r["position_pct"])
        e["last_position_date"] = max(e["last_position_date"], r["position_date"])
    out = []
    for e in by_isin.values():
        total = _canonical_pct_total(e.pop("pcts"))
        e["disclosed_total"] = _pct_str(total)
        out.append(e)
    out.sort(key=lambda e: (-float(e["disclosed_total"]), e["issuer_name"]))
    return out


def holder_current_ranking(conn: sqlite3.Connection, snapshot_sha256: str) -> list[dict]:
    """Per-holder aggregation over the snapshot's Current sheet."""
    from .. import constants

    rows = conn.execute(
        """SELECT d.holder_name, d.isin, d.position_pct, d.position_date
           FROM disclosure d
           JOIN snapshot_disclosure sd ON sd.disclosure_id = d.disclosure_id
           WHERE sd.snapshot_sha256 = ? AND sd.sheet_name = ?""",
        (snapshot_sha256, constants.SHEET_CURRENT),
    ).fetchall()
    by_holder: dict[str, dict] = {}
    for r in rows:
        e = by_holder.setdefault(
            r["holder_name"],
            {
                "holder_name": r["holder_name"],
                "positions": 0,
                "isins": set(),
                "pcts": [],
                "last_position_date": "",
            },
        )
        e["positions"] += 1
        e["isins"].add(r["isin"])
        e["pcts"].append(r["position_pct"])
        e["last_position_date"] = max(e["last_position_date"], r["position_date"])
    out = []
    for e in by_holder.values():
        total = _canonical_pct_total(e.pop("pcts"))
        e["issuers"] = len(e.pop("isins"))
        e["disclosed_total"] = _pct_str(total)
        out.append(e)
    out.sort(key=lambda e: (-e["positions"], -float(e["disclosed_total"]), e["holder_name"]))
    return out


def latest_current_rows(
    conn: sqlite3.Connection, snapshot_sha256: str, limit: int = 12
) -> list[sqlite3.Row]:
    """Most recent position dates on the Current sheet (publication moves)."""
    from .. import constants

    return conn.execute(
        """SELECT d.* FROM disclosure d
           JOIN snapshot_disclosure sd ON sd.disclosure_id = d.disclosure_id
           WHERE sd.snapshot_sha256 = ? AND sd.sheet_name = ?
           ORDER BY d.position_date DESC, d.isin
           LIMIT ?""",
        (snapshot_sha256, constants.SHEET_CURRENT, limit),
    ).fetchall()


def current_total_pct(conn: sqlite3.Connection, snapshot_sha256: str, isin: str) -> str | None:
    """Exact disclosed total for one ISIN on the Current sheet, computed
    with Decimal over the canonical strings (no float)."""
    from decimal import Decimal

    from .. import constants

    rows = conn.execute(
        """SELECT d.position_pct FROM disclosure d
           JOIN snapshot_disclosure sd ON sd.disclosure_id = d.disclosure_id
           WHERE sd.snapshot_sha256 = ? AND sd.sheet_name = ? AND d.isin = ?""",
        (snapshot_sha256, constants.SHEET_CURRENT, isin),
    ).fetchall()
    if not rows:
        return None
    total = sum(Decimal(r["position_pct"]) for r in rows)
    if total == total.to_integral():
        return str(total.quantize(Decimal(1)))
    return format(total.normalize(), "f")


def first_observed_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MIN(first_observed_at) FROM disclosure").fetchone()
    return row[0] if row else None


def decimal_of(row: sqlite3.Row) -> Decimal:
    return Decimal(row["position_pct"])


def disclosure_ids_since_snapshot(conn: sqlite3.Connection, sha256: str) -> Iterable[str]:
    return (
        r[0]
        for r in conn.execute(
            "SELECT disclosure_id FROM disclosure WHERE first_snapshot_sha256 = ?",
            (sha256,),
        )
    )
