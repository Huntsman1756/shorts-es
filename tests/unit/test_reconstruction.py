"""Reconstruction, states, diff and verification over the fixture dataset."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from shorts_es import constants
from shorts_es.domain import reconstruction, temporal, verification
from shorts_es.domain.diff import diff_snapshots
from shorts_es.domain.states import DisclosureState
from shorts_es.exceptions import MissingSnapshotError
from shorts_es.storage import repository as repo


def _latest_sha(conn):
    return repo.latest_snapshot(conn)["snapshot_sha256"]


def test_latest_per_pair(conn):
    rows = repo.disclosures_for_issuer(conn, "ES0125220311")
    latest = reconstruction.latest_per_pair(rows)
    blackrock = latest[("54930002KP75TLLLNO21", "ES0125220311",
                        "BlackRock Investment Management (UK) Limited")]
    assert blackrock["position_date"] == "2026-08-04"
    assert blackrock["position_pct"] == "0.62"


def test_closed_pair_state_is_zero(conn):
    rows = repo.disclosures_for_issuer(conn, "ES0125220311")
    latest = reconstruction.latest_per_pair(rows)
    mw = latest[("54930002KP75TLLLNO21", "ES0125220311", "Marshall Wace LLP")]
    assert mw["position_pct"] == "0"
    assert mw["position_date"] == "2021-02-19"


def test_effective_at_filtering(conn):
    rows = repo.disclosures_for_issuer(conn, "ES0125220311")
    latest = reconstruction.latest_per_pair(rows, effective_at=date(2021, 2, 1))
    mw = latest[("54930002KP75TLLLNO21", "ES0125220311", "Marshall Wace LLP")]
    # before the closing notifications of 2021-02-18/19, MW stood at 0.66.
    assert mw["position_date"] == "2021-01-26"
    assert mw["position_pct"] == "0.66"
    # and entirely absent before any publication
    none = reconstruction.latest_per_pair(rows, effective_at=date(2020, 1, 1))
    assert ("54930002KP75TLLLNO21", "ES0125220311", "Marshall Wace LLP") not in none


def test_issuer_states_sorted_and_flagged(conn):
    sha = _latest_sha(conn)
    cur = reconstruction.current_pair_keys(conn, sha)
    states = reconstruction.issuer_states(conn, "ES0125220311", current_pairs=cur)
    in_cur = [s for s in states if s.in_current_sheet]
    assert {s.holder_name for s in in_cur} == {
        "BlackRock Investment Management (UK) Limited",
        "AQR Capital Management, LLC",
    }
    # below-threshold current publication is still OPEN
    aqr = next(s for s in in_cur if s.holder_name == "AQR Capital Management, LLC")
    assert aqr.state == DisclosureState.PUBLIC_POSITION_OPEN
    assert not aqr.above_public_threshold


def test_pair_case_variant_merges_into_one_series(conn):
    """The eS0118594417 typo row belongs to the ES0118594417 pair."""
    rows = repo.disclosures_for_issuer(conn, "ES0118594417")
    dates = {r["position_date"] for r in rows}
    assert "2014-12-23" in dates
    latest = reconstruction.latest_per_pair(rows)
    aqr = latest[("95980020140005308793", "ES0118594417",
                  "AQR Capital Management, LLC")]
    assert aqr["position_pct"] == "1.49"
    # the 2014 typo row is part of the same pair's history (queried above)


def test_verification_passes_on_consistent_workbook(conn):
    sha = _latest_sha(conn)
    result = verification.verify_snapshot(conn, sha)
    assert result.passed, result.details()
    assert result.pairs_checked == 5
    assert result.matched == 5


def test_knowledge_time_guard(conn):
    first = repo.first_observed_at(conn)
    assert first is not None
    # all fixture disclosures share the same first_observed (reconstructed)
    rows = repo.disclosures_for_issuer(conn, "ES0125220311")
    assert {r["first_observed_at"] for r in rows} == {first}


def test_known_at_cutoff_limits_rows(conn):
    sha = _latest_sha(conn)
    snap = repo.get_snapshot(conn, sha)
    all_rows = repo.disclosures_for_issuer(conn, "ES0125220311")
    cutoff = datetime.fromisoformat(snap["retrieved_at"]).astimezone(UTC)
    rows = repo.disclosures_for_issuer(
        conn, "ES0125220311", known_at=temporal.iso_utc(cutoff)
    )
    assert len(rows) == len(all_rows)
    rows_before = repo.disclosures_for_issuer(
        conn, "ES0125220311", known_at="2000-01-01T00:00:00+00:00"
    )
    assert rows_before == []


def test_diff_same_snapshot_is_empty(conn):
    sha = _latest_sha(conn)
    d = diff_snapshots(conn, sha, sha)
    assert d.added_ids == set()
    assert d.removed_ids == set()
    assert d.changes == []


def test_diff_missing_snapshot_errors(conn):
    with pytest.raises(MissingSnapshotError):
        diff_snapshots(conn, "0" * 64, "f" * 64)


def test_previous_duplicate_rows_preserve_provenance(conn):
    """The duplicated Citadel row exists once as a disclosure but twice as
    physical rows - both must be traceable."""
    rows = conn.execute(
        "SELECT disclosure_id FROM disclosure WHERE holder_name = ? AND position_date = ?",
        ("Citadel Advisors Europe Limited", "2025-06-06"),
    ).fetchall()
    assert len(rows) == 1
    did = rows[0]["disclosure_id"]
    locs = repo.disclosure_provenance(conn, did)
    prev_rows = [l for l in locs if l["sheet_name"] == constants.SHEET_PREVIOUS]
    assert len(prev_rows) == 2
    assert {l["row_number"] for l in prev_rows} == {10, 11}


def test_holder_states(conn):
    sha = _latest_sha(conn)
    cur = reconstruction.current_pair_keys(conn, sha)
    states = reconstruction.holder_states(
        conn, "AQR Capital Management, LLC", current_pairs=cur
    )
    assert len(states) >= 2
    by_isin = {s.isin: s for s in states}
    assert by_isin["ES0118594417"].position_pct == Decimal("1.49")
    assert by_isin["ES0118594417"].in_current_sheet
