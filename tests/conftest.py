import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

from builder import CURRENT_A, PREVIOUS_A, SERIES_A, build_workbook

from shorts_es.config import Config
from shorts_es.pipeline import sync


@pytest.fixture()
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture()
def config(data_dir):
    return Config.resolve(data_dir)


@pytest.fixture()
def workbook_bytes():
    return build_workbook(current=CURRENT_A, series=SERIES_A, previous=PREVIOUS_A)


@pytest.fixture()
def workbook_path(tmp_path, workbook_bytes):
    p = tmp_path / "NetShortPositions.xls"
    p.write_bytes(workbook_bytes)
    return p


@pytest.fixture()
def synced(config, workbook_path):
    """A config with the fixture workbook ingested."""
    result = sync(config, file=str(workbook_path))
    assert result.status == "CREATED"
    return config, result


@pytest.fixture()
def conn(synced):
    from shorts_es.storage import db

    c = db.open_db(synced[0].db_path)
    yield c
    c.close()


@pytest.fixture()
def real_workbook():
    """The captured production workbook, if present (never committed)."""
    for cand in (
        Path(__file__).resolve().parents[1] / "_probe" / "NetShortPositions.xls",
        Path.cwd() / "_probe" / "NetShortPositions.xls",
    ):
        if cand.exists():
            return cand
    return None


@pytest.fixture()
def fresh_dir(tmp_path):
    d = tmp_path / "fresh"
    shutil.rmtree(d, ignore_errors=True)
    return d
