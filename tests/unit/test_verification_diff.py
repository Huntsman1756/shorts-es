"""Verification failure modes + snapshot diff over changing sources."""

from builder import CURRENT_A, PREVIOUS_A, SERIES_A, build_workbook, row

from shorts_es.domain import verification
from shorts_es.domain.diff import diff_snapshots
from shorts_es.pipeline import sync


def _v2_workbook() -> bytes:
    """A second publication: BlackRock/A raises to 0.78, AQR/A drops out of
    Current, a pre-existing pair (Qube/B) publishes a new latest, and a
    brand-new pair appears on issuer C."""
    series = SERIES_A.copy()
    series.insert(
        0,
        row(
            "54930002KP75TLLLNO21",
            "ES0125220311",
            "ACCIONA, S.A.",
            "BlackRock Investment Management (UK) Limited",
            "2026-10-06",
            0.78,
        ),
    )
    current = [
        row(
            "54930002KP75TLLLNO21",
            "ES0125220311",
            "ACCIONA, S.A.",
            "BlackRock Investment Management (UK) Limited",
            "2026-10-06",
            0.78,
        ),
        row(
            "959800R7QMXKF0NFMT29",
            "ES0105046017",
            "AENA, S.M.E., S.A.",
            "BlackRock Investment Management (UK) Limited",
            "2026-09-14",
            0.51,
        ),
        row(
            "959800R7QMXKF0NFMT29",
            "ES0105046017",
            "AENA, S.M.E., S.A.",
            "Qube Research & Technologies Ltd",
            "2026-10-05",
            0.52,
        ),
        row(
            "95980020140005308793",
            "ES0118594417",
            "FERROVIAL, S.A.",
            "AQR Capital Management, LLC",
            "2026-10-02",
            1.49,
        ),
        row(
            "95980020140005308793",
            "ES0118594417",
            "FERROVIAL, S.A.",
            "New Entrant Capital LLP",
            "2026-10-05",
            0.6,
        ),
    ]
    series.insert(
        8,
        row(
            "959800R7QMXKF0NFMT29",
            "ES0105046017",
            "AENA, S.M.E., S.A.",
            "Qube Research & Technologies Ltd",
            "2026-10-05",
            0.52,
        ),
    )
    series.insert(
        10,
        row(
            "95980020140005308793",
            "ES0118594417",
            "FERROVIAL, S.A.",
            "New Entrant Capital LLP",
            "2026-10-05",
            0.6,
        ),
    )
    return build_workbook(
        current=current, series=series, previous=PREVIOUS_A, publication_date="2026-10-07"
    )


def test_two_snapshot_diff(config, workbook_path, tmp_path):
    r1 = sync(config, file=str(workbook_path))
    p2 = tmp_path / "wb2.xls"
    p2.write_bytes(_v2_workbook())
    r2 = sync(config, file=str(p2))
    assert r2.status == "CREATED"
    assert r2.sha256 != r1.sha256

    from shorts_es.storage import db

    conn = db.open_db(config.db_path)
    d = diff_snapshots(conn, r1.sha256, r2.sha256)
    kinds = {(c.isin, c.holder_name, c.kind) for c in d.changes}
    assert ("ES0125220311", "BlackRock Investment Management (UK) Limited", "CHANGED") in kinds
    # Qube/B already had a published value in snapshot A -> CHANGED, not ADDED
    qube = next(c for c in d.changes if c.holder_name == "Qube Research & Technologies Ltd")
    assert qube.kind == "CHANGED" and qube.direction == "INCREASED"
    added = [c for c in d.changes if c.kind == "ADDED"]
    assert any(c.holder_name == "New Entrant Capital LLP" for c in added)
    assert len(d.added_ids) >= 2  # new rows appeared
    conn.close()


def test_verification_detects_removed_current_row(config, tmp_path):
    """If Current drops a pair that Series still lists, verify reports
    'unexpected'."""
    wb = build_workbook(current=CURRENT_A[1:], series=SERIES_A, previous=PREVIOUS_A)
    p = tmp_path / "bad.xls"
    p.write_bytes(wb)
    r = sync(config, file=str(p))
    from shorts_es.storage import db

    conn = db.open_db(config.db_path)
    res = verification.verify_snapshot(conn, r.sha256)
    assert not res.passed
    assert len(res.unexpected) == 1
    assert res.unexpected[0].holder_name == "BlackRock Investment Management (UK) Limited"
    conn.close()


def test_verification_detects_pct_conflict(config, tmp_path):
    """Current row whose pct disagrees with the latest Series row."""
    current = CURRENT_A.copy()
    current[0] = row(
        "54930002KP75TLLLNO21",
        "ES0125220311",
        "ACCIONA, S.A.",
        "BlackRock Investment Management (UK) Limited",
        "2026-08-04",
        0.99,
    )
    wb = build_workbook(current=current, series=SERIES_A, previous=PREVIOUS_A)
    p = tmp_path / "conflict.xls"
    p.write_bytes(wb)
    r = sync(config, file=str(p))
    from shorts_es.storage import db

    conn = db.open_db(config.db_path)
    res = verification.verify_snapshot(conn, r.sha256)
    assert not res.passed
    assert len(res.conflicts) == 1
    conn.close()


def test_verification_detects_missing_series_pair(config, tmp_path):
    """Current lists a pair absent from Series entirely."""
    current = [
        *CURRENT_A,
        row(
            "54930002KP75TLLLNO21",
            "ES0125220311",
            "ACCIONA, S.A.",
            "Ghost Capital",
            "2026-10-05",
            0.7,
        ),
    ]
    wb = build_workbook(current=current, series=SERIES_A, previous=PREVIOUS_A)
    p = tmp_path / "ghost.xls"
    p.write_bytes(wb)
    r = sync(config, file=str(p))
    from shorts_es.storage import db

    conn = db.open_db(config.db_path)
    res = verification.verify_snapshot(conn, r.sha256)
    assert not res.passed
    assert len(res.missing) == 1
    assert res.missing[0].holder_name == "Ghost Capital"
    conn.close()
