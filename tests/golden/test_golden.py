"""Golden cases: 23 hand-verified rows from the real CNMV workbook.

Two layers:
1. ``test_golden_ids_are_stable`` always runs: rebuilding disclosures from the
   recorded canonical fields must reproduce the recorded ids. This pins the
   identity function.
2. ``test_real_workbook_golden_rows`` runs only when a captured production
   workbook is available (``_probe/`` or ``SHORTS_ES_PROBE``): it verifies
   the parser produces exactly the recorded canonical rows - sheet, row
   number, values and identity included.
"""

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from shorts_es import constants
from shorts_es.parser.models import Disclosure
from shorts_es.parser.workbook import parse_workbook

GOLDEN_FILE = Path(__file__).parent / "golden_rows.jsonl"


def _golden() -> list[dict]:
    return [
        json.loads(line) for line in GOLDEN_FILE.read_text("utf-8").splitlines() if line.strip()
    ]


def test_golden_file_has_enough_cases():
    assert len(_golden()) >= 20


def test_golden_ids_are_stable():
    for g in _golden():
        d = Disclosure(
            lei=g["lei"],
            isin=g["isin"],
            issuer_name=g["issuer_name"],
            holder_name=g["holder_name"],
            position_date=date.fromisoformat(g["position_date"]),
            position_pct=Decimal(g["position_pct"]),
        )
        assert d.disclosure_id == g["disclosure_id"], g


def _real_workbook_path() -> Path | None:
    env = os.environ.get("SHORTS_ES_PROBE")
    if env and Path(env).is_file():
        return Path(env)
    probe = Path(__file__).resolve().parents[2] / "_probe" / "NetShortPositions.xls"
    return probe if probe.is_file() else None


def test_real_workbook_golden_rows():
    path = _real_workbook_path()
    if path is None:
        pytest.skip("no captured production workbook available")
    parsed = parse_workbook(path.read_bytes())
    seen = {}
    for r in parsed.rows:
        seen.setdefault(r.disclosure.disclosure_id, []).append(r)
    for g in _golden():
        assert g["disclosure_id"] in seen, f"missing golden case {g['case']}"
        locs = seen[g["disclosure_id"]]
        assert any(
            loc.sheet_name == g["sheet"] and loc.row_number == g["row_number"] for loc in locs
        ), f"case {g['case']}: expected {g['sheet']} row {g['row_number']}"


def test_real_workbook_core_invariants():
    """Production-level invariants verified against the real capture."""
    path = _real_workbook_path()
    if path is None:
        pytest.skip("no captured production workbook available")
    parsed = parse_workbook(path.read_bytes())
    rows = parsed.rows
    cur = [r for r in rows if r.sheet_name == constants.SHEET_CURRENT]
    ser = [r for r in rows if r.sheet_name == constants.SHEET_SERIES]
    ser_ids = {r.disclosure.disclosure_id for r in ser}
    # Current is an exact subset of Series.
    assert all(r.disclosure.disclosure_id in ser_ids for r in cur)
    # No same-pair same-date conflicting values anywhere.
    pair_date = {}
    for r in rows:
        d = r.disclosure
        key = (d.pair_key, d.position_date)
        assert pair_date.get(key, d.position_pct) == d.position_pct
        pair_date[key] = d.position_pct
