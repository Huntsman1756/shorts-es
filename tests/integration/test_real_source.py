"""Integration test against the captured production workbook.

Requires ``_probe/NetShortPositions.xls`` or ``SHORTS_ES_PROBE``. Exercises
the whole pipeline end to end: sync -> verify -> queries.
"""

import os
from pathlib import Path

import pytest

from shorts_es import constants
from shorts_es.config import Config
from shorts_es.domain import verification
from shorts_es.pipeline import sync
from shorts_es.storage import db
from shorts_es.storage import repository as repo

EXPECTED_SHA256 = "6d9ea43b460bca3cb321018bd4da6b5e0708105a8e1d5505bac5fb8435cba5e9"


def _probe() -> Path:
    env = os.environ.get("SHORTS_ES_PROBE")
    if env and Path(env).is_file():
        return Path(env)
    p = Path(__file__).resolve().parents[2] / "_probe" / "NetShortPositions.xls"
    if not p.is_file():
        pytest.skip("captured production workbook not available")
    return p


def test_full_pipeline_on_real_workbook(tmp_path):
    config = Config.resolve(tmp_path / "data")
    result = sync(config, file=str(_probe()))
    assert result.status == "CREATED"
    assert result.sha256 == EXPECTED_SHA256
    assert result.total_rows == 14743
    assert result.new_disclosures == 12252

    conn = db.open_db(config.db_path)
    res = verification.verify_snapshot(conn, result.sha256)
    assert res.passed, res.details()
    assert res.pairs_checked == 63

    stats = repo.dataset_stats(conn)
    assert stats["issuers"] == 90
    assert stats["holders"] == 228

    # second sync is a no-op
    r2 = sync(config, file=str(_probe()))
    assert r2.status == "NO_CHANGE"
    conn.close()


@pytest.mark.live()
def test_live_source_fetch(tmp_path):
    """Fetches the real CNMV URL. Marked 'live'; excluded from the default
    suite and CI."""
    config = Config.resolve(tmp_path / "data")
    result = sync(config, url=constants.SOURCE_URL)
    assert result.status in ("CREATED", "NO_CHANGE")
    conn = db.open_db(config.db_path)
    assert repo.latest_snapshot(conn) is not None
    conn.close()
