"""Tests for data audit features: integrity, retention, idempotency."""

import pytest
from fastapi.testclient import TestClient

from shorts_es.config import Config
from shorts_es.pipeline import sync
from shorts_es.storage import db, repository as repo
from shorts_es.web.app import create_app
from tests.fixtures.builder import build_workbook, SERIES_A, PREVIOUS_A


# -------------------------------------------------------------- fixtures


@pytest.fixture()
def client(config, workbook_path):
    """FastAPI test client over synced data."""
    config.ensure_dirs()
    sync(config, file=str(workbook_path))
    return TestClient(create_app(config))


# -------------------------------------------------------------- integrity_check


class TestIntegrityCheck:
    """PRAGMA integrity_check via CLI and API."""

    def test_integrity_api_ok(self, client):
        r = client.get("/api/v1/integrity")
        assert r.status_code == 200
        data = r.json()
        assert data["integrity"] == "ok"
        assert data["stats"]["disclosures"] > 0

    def test_integrity_stats(self, client):
        r = client.get("/api/v1/integrity")
        stats = r.json()["stats"]
        # fixture creates 5 rows, but may be >5 if tests share tmp_path
        assert stats["disclosures"] >= 5
        assert stats["issuers"] >= 1


# -------------------------------------------------------------- retention


class TestRetention:
    """Snapshot retention: enforce_retention removes old .xls files."""

    def test_retention_no_op_when_zero(self, tmp_path):
        """max_snapshots=0 should not remove anything."""
        import tempfile
        from shorts_es.storage import db as db_mod
        
        cfg = Config.resolve(tmp_path / "data")
        cfg.ensure_dirs()
        # Create a minimal db
        conn = db_mod.open_db(cfg.db_path)
        conn.execute("INSERT INTO meta (key, value) VALUES ('latest_snapshot', 'test')")
        conn.execute(
            "INSERT INTO snapshot (snapshot_sha256, retrieved_at, source_url, status, raw_path, parser_version, schema_fingerprint) "
            "VALUES ('aaa', '2026-01-01', 'http://test', 'parsed', '/tmp/a', 'v1', 'fp')",
        )
        conn.commit()
        result = repo.enforce_retention(conn, cfg.snapshots_dir, 0)
        conn.close()
        assert result["removed"] == []
        assert result["total"] == 1

    def test_retention_removes_when_exceeded(self, tmp_path):
        """max_snapshots=1 should keep only the latest."""
        from shorts_es.storage import db as db_mod
        
        cfg = Config.resolve(tmp_path / "data")
        cfg.ensure_dirs()
        conn = db_mod.open_db(cfg.db_path)
        # Insert 3 snapshots
        for i in range(3):
            conn.execute(
                "INSERT INTO snapshot (snapshot_sha256, retrieved_at, source_url, status, raw_path, parser_version, schema_fingerprint) "
                f"VALUES ('sha{i:02d}', '2026-01-0{i+1}', 'http://test', 'parsed', '/tmp/a', 'v1', 'fp')",
            )
        conn.commit()
        result = repo.enforce_retention(conn, cfg.snapshots_dir, 1)
        conn.close()
        assert len(result["removed"]) == 2
        assert result["total"] == 3

    def test_retention_preserves_xls_files(self, tmp_path):
        """Retained snapshots still have their .xls files on disk."""
        from shorts_es.storage import db as db_mod
        
        cfg = Config.resolve(tmp_path / "data")
        cfg.ensure_dirs()
        (cfg.snapshots_dir / "existing.xls").write_bytes(b"fake")
        conn = db_mod.open_db(cfg.db_path)
        conn.execute(
            "INSERT INTO snapshot (snapshot_sha256, retrieved_at, source_url, status, raw_path, parser_version, schema_fingerprint) "
            "VALUES ('aaa', '2026-01-01', 'http://test', 'parsed', '/tmp/a', 'v1', 'fp')",
        )
        conn.commit()
        result = repo.enforce_retention(conn, cfg.snapshots_dir, 100)
        conn.close()
        xls_files = list(cfg.snapshots_dir.glob("*.xls"))
        assert len(xls_files) >= 1


# -------------------------------------------------------------- idempotency


class TestIdempotency:
    """Re-running sync should not duplicate data."""

    def test_sync_twice_no_duplicate_disclosures(self, config, workbook_path, conn):
        count1 = conn.execute("SELECT COUNT(*) FROM disclosure").fetchone()[0]
        result2 = sync(config, file=str(workbook_path))
        assert result2.status == "NO_CHANGE"
        count2 = conn.execute("SELECT COUNT(*) FROM disclosure").fetchone()[0]
        assert count1 == count2, "Disclosures should not be duplicated on re-sync"

    def test_sync_twice_no_duplicate_snapshot(self, config, workbook_path, conn):
        snap_count1 = conn.execute("SELECT COUNT(*) FROM snapshot").fetchone()[0]
        sync(config, file=str(workbook_path))
        snap_count2 = conn.execute("SELECT COUNT(*) FROM snapshot").fetchone()[0]
        assert snap_count1 == snap_count2, "Snapshots should not be duplicated"

    def test_sync_twice_no_duplicate_snapshot_disclosure(self, config, workbook_path, conn):
        sd_count1 = conn.execute("SELECT COUNT(*) FROM snapshot_disclosure").fetchone()[0]
        sync(config, file=str(workbook_path))
        sd_count2 = conn.execute("SELECT COUNT(*) FROM snapshot_disclosure").fetchone()[0]
        assert sd_count1 == sd_count2

    def test_sync_twice_first_observed_preserved(self, config, workbook_path, conn):
        first1 = conn.execute(
            "SELECT first_observed_at FROM disclosure ORDER BY first_observed_at LIMIT 1"
        ).fetchone()[0]
        sync(config, file=str(workbook_path))
        first2 = conn.execute(
            "SELECT first_observed_at FROM disclosure ORDER BY first_observed_at LIMIT 1"
        ).fetchone()[0]
        assert first1 == first2


# -------------------------------------------------------------- corrupt content


class TestCorruptContent:
    """Corrupt or empty content should not break the database."""

    def test_corrupt_xls_rejected(self, tmp_path):
        """A fake .xls file should fail gracefully."""
        cfg = Config.resolve(tmp_path / "data")
        cfg.ensure_dirs()
        fake = cfg.data_dir / "fake.xls"
        fake.write_bytes(b"This is not a real Excel file")
        result = sync(cfg, file=str(fake))
        assert result.status in ("SCHEMA_DRIFT", "PARSE_ERROR")
        conn = db.open_db(cfg.db_path)
        result_integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        assert result_integrity == "ok"

    def test_empty_xls_rejected(self, tmp_path):
        """An empty file should fail gracefully."""
        cfg = Config.resolve(tmp_path / "data")
        cfg.ensure_dirs()
        fake = cfg.data_dir / "empty.xls"
        fake.write_bytes(b"")
        result = sync(cfg, file=str(fake))
        assert result.status in ("SCHEMA_DRIFT", "PARSE_ERROR")
        conn = db.open_db(cfg.db_path)
        result_integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        assert result_integrity == "ok"