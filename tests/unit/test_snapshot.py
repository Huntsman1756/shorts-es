"""Snapshot storage invariants."""

import json

from shorts_es.pipeline import sync
from shorts_es.source.fetch import fetch_local
from shorts_es.source.snapshot import (
    sha256_bytes,
    snapshot_path,
    store_snapshot,
)


def test_same_content_same_sha(workbook_bytes):
    assert sha256_bytes(workbook_bytes) == sha256_bytes(bytes(workbook_bytes))


def test_different_content_different_sha(workbook_bytes):
    assert sha256_bytes(workbook_bytes) != sha256_bytes(workbook_bytes + b"x")


def test_store_is_idempotent(config, workbook_path):
    f1 = fetch_local(workbook_path)
    s1 = store_snapshot(config, f1)
    assert not s1.already_existed
    s2 = store_snapshot(config, fetch_local(workbook_path))
    assert s2.already_existed
    assert s1.sha256 == s2.sha256
    assert s1.raw_path == s2.raw_path


def test_second_sync_no_duplicate_snapshot(config, workbook_path):
    r1 = sync(config, file=str(workbook_path))
    assert r1.status == "CREATED"
    r2 = sync(config, file=str(workbook_path))
    assert r2.status == "NO_CHANGE"
    files = list(config.snapshots_dir.glob("*.xls"))
    assert len(files) == 1


def test_raw_bytes_roundtrip(config, workbook_path, workbook_bytes):
    sync(config, file=str(workbook_path))
    sha = sha256_bytes(workbook_bytes)
    assert snapshot_path(config, sha).read_bytes() == workbook_bytes


def test_manifest_written(config, workbook_path):
    sync(config, file=str(workbook_path))
    lines = config.manifest_path.read_text("utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["sha256"] == sha256_bytes(workbook_path.read_bytes())
    assert entry["status"] == "parsed"
    assert entry["schema_fingerprint"]
    assert "Serie_-_Series" in entry["rows"]


def test_sync_preserves_http_metadata(config, workbook_path):
    r = sync(config, file=str(workbook_path))
    from shorts_es.storage import db

    conn = db.open_db(config.db_path)
    snap = conn.execute(
        "SELECT * FROM snapshot WHERE snapshot_sha256 = ?", (r.sha256,)
    ).fetchone()
    assert snap["source_url"].endswith("NetShortPositions.xls")
    assert snap["parser_version"] == "cnmv-nsp-parser/1"
    assert snap["status"] == "parsed"
    assert snap["publication_date"] == "2026-10-06"
    conn.close()
