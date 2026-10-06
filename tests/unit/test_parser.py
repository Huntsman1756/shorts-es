"""Parser determinism and normalization tests."""

from datetime import date
from decimal import Decimal

import pytest
from builder import H_UNICODE, ISIN_A, ISIN_C, LEI_A, build_workbook

from shorts_es import constants
from shorts_es.exceptions import ParseError, SchemaDriftError, UnsupportedWorkbookError
from shorts_es.parser.models import Disclosure
from shorts_es.parser.workbook import parse_workbook


def test_parse_is_deterministic(workbook_bytes):
    a = parse_workbook(workbook_bytes)
    b = parse_workbook(workbook_bytes)
    assert a == b
    assert [r.disclosure.disclosure_id for r in a.rows] == [
        r.disclosure.disclosure_id for r in b.rows
    ]


def test_publication_date_extracted(workbook_bytes):
    parsed = parse_workbook(workbook_bytes)
    assert parsed.publication_date == date(2026, 10, 6)


def test_row_counts_and_sheets(workbook_bytes):
    parsed = parse_workbook(workbook_bytes)
    by_sheet = {}
    for r in parsed.rows:
        by_sheet.setdefault(r.sheet_name, []).append(r)
    assert len(by_sheet[constants.SHEET_CURRENT]) == 5
    assert len(by_sheet[constants.SHEET_SERIES]) == 11
    assert len(by_sheet[constants.SHEET_PREVIOUS]) == 14


def test_row_numbers_are_one_based(workbook_bytes):
    parsed = parse_workbook(workbook_bytes)
    first = parsed.rows[0]
    assert first.sheet_name == constants.SHEET_CURRENT
    assert first.row_number == 5  # header is row 4, data starts row 5


def test_decimal_exactness_three_places(workbook_bytes):
    parsed = parse_workbook(workbook_bytes)
    pcts = {r.disclosure.position_pct for r in parsed.rows}
    assert Decimal("0.492") in pcts
    assert Decimal("0.599") in pcts
    assert Decimal("0.609") in pcts
    assert Decimal("0.02") in pcts
    assert Decimal("4.49") in pcts
    assert Decimal("0") in pcts


def test_pct_canonical_rendering(workbook_bytes):
    parsed = parse_workbook(workbook_bytes)
    strs = {r.disclosure.pct_str for r in parsed.rows}
    assert "0.5" in strs and "1" in strs  # 0.50 -> '0.5', 1.00 -> '1'
    assert all("e" not in s.lower() for s in strs)


def test_isin_case_normalized_into_one_disclosure(workbook_bytes):
    parsed = parse_workbook(workbook_bytes)
    isins = {r.disclosure.isin for r in parsed.rows}
    assert ISIN_C in isins
    assert "eS0118594417" not in isins


def test_unicode_names_preserved(workbook_bytes):
    parsed = parse_workbook(workbook_bytes)
    holders = {r.disclosure.holder_name for r in parsed.rows}
    assert H_UNICODE in holders


def test_disclosure_id_ignores_sheet_and_row(workbook_bytes):
    """Same content in Current and Series -> one identity."""
    parsed = parse_workbook(workbook_bytes)
    cur = [r for r in parsed.rows if r.sheet_name == constants.SHEET_CURRENT]
    ser = [r for r in parsed.rows if r.sheet_name == constants.SHEET_SERIES]
    ser_ids = {r.disclosure.disclosure_id for r in ser}
    for r in cur:
        assert r.disclosure.disclosure_id in ser_ids


def test_same_semantic_value_different_repr_merges():
    """0.60 and 0.6 are the same number -> same disclosure id."""
    d1 = Disclosure(LEI_A, ISIN_A, "X", "Y", date(2020, 1, 1), Decimal("0.60"))
    d2 = Disclosure(LEI_A, ISIN_A, "X", "Y", date(2020, 1, 1), Decimal("0.6"))
    assert d1.disclosure_id == d2.disclosure_id
    assert d1.canonical_json() == d2.canonical_json()


def test_id_stable_across_construction(workbook_bytes):
    parsed1 = parse_workbook(workbook_bytes)
    parsed2 = parse_workbook(workbook_bytes)
    ids1 = sorted(r.disclosure.disclosure_id for r in parsed1.rows)
    ids2 = sorted(r.disclosure.disclosure_id for r in parsed2.rows)
    assert ids1 == ids2


# ------------------------------------------------------------ fail-closed


def test_non_ole2_rejected():
    with pytest.raises(UnsupportedWorkbookError):
        parse_workbook(b"<html><table>not a workbook</table></html>")


def test_bad_header_fails_closed(workbook_bytes):
    from io import BytesIO

    import xlwt

    wb = xlwt.Workbook()
    sh = wb.add_sheet(constants.SHEET_METADATA)
    sh.write(3, 1, " 2026-10-06 ")
    bad = wb.add_sheet(constants.SHEET_CURRENT)
    headers = list(constants.EXPECTED_HEADERS)
    headers[0] = "LEI_CODE"  # renamed column
    for c, h in enumerate(headers):
        bad.write(3, c, h)
    bad.write(4, 0, "x")
    for name in (constants.SHEET_SERIES, constants.SHEET_PREVIOUS):
        wb.add_sheet(name)
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(SchemaDriftError):
        parse_workbook(buf.getvalue())


def test_missing_sheet_fails_closed():
    from io import BytesIO

    import xlwt

    wb = xlwt.Workbook()
    wb.add_sheet(constants.SHEET_METADATA)
    wb.add_sheet(constants.SHEET_CURRENT)
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(SchemaDriftError):
        parse_workbook(buf.getvalue())


def test_unexpected_nonempty_sheet_fails_closed():
    from io import BytesIO

    import xlwt
    from builder import CURRENT_A, PREVIOUS_A, SERIES_A

    wb = xlwt.Workbook()
    wb.add_sheet(constants.SHEET_METADATA)
    from builder import _write_data_sheet

    _write_data_sheet(wb, constants.SHEET_CURRENT, CURRENT_A)
    _write_data_sheet(wb, constants.SHEET_SERIES, SERIES_A)
    _write_data_sheet(wb, constants.SHEET_PREVIOUS, PREVIOUS_A)
    surprise = wb.add_sheet("Surprise")
    surprise.write(0, 0, "data")
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(SchemaDriftError):
        parse_workbook(buf.getvalue())


def test_numeric_date_cell_fails_closed():
    """A date stored as a number cell instead of text must fail, not coerce."""
    # craft manually: put a float into the date column
    from io import BytesIO

    import xlwt
    from builder import CURRENT_A, PREVIOUS_A, SERIES_A

    wb = xlwt.Workbook()
    wb.add_sheet(constants.SHEET_METADATA)
    from builder import _write_data_sheet

    sh = wb.add_sheet(constants.SHEET_CURRENT)
    for c, h in enumerate(constants.EXPECTED_HEADERS):
        sh.write(3, c, h)
    r = list(CURRENT_A[0])
    r[4] = 45000.0  # numeric date
    for c, v in enumerate(r):
        sh.write(4, c, v)
    _write_data_sheet(wb, constants.SHEET_SERIES, SERIES_A)
    _write_data_sheet(wb, constants.SHEET_PREVIOUS, PREVIOUS_A)
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(ParseError):
        parse_workbook(buf.getvalue())


def test_negative_pct_fails():
    from io import BytesIO

    import xlwt
    from builder import CURRENT_A, PREVIOUS_A, SERIES_A, _write_data_sheet

    wb = xlwt.Workbook()
    wb.add_sheet(constants.SHEET_METADATA)
    sh = wb.add_sheet(constants.SHEET_CURRENT)
    for c, h in enumerate(constants.EXPECTED_HEADERS):
        sh.write(3, c, h)
    r = list(CURRENT_A[0])
    r[5] = -0.5
    for c, v in enumerate(r):
        sh.write(4, c, v)
    _write_data_sheet(wb, constants.SHEET_SERIES, SERIES_A)
    _write_data_sheet(wb, constants.SHEET_PREVIOUS, PREVIOUS_A)
    buf = BytesIO()
    wb.save(buf)
    with pytest.raises(ParseError):
        parse_workbook(buf.getvalue())


def test_pair_key(workbook_bytes):
    parsed = parse_workbook(workbook_bytes)
    d = parsed.rows[0].disclosure
    assert d.pair_key == (d.lei, d.isin, d.holder_name)


def test_parse_result_is_order_independent_as_set(workbook_bytes):
    """Disclosure identity set does not depend on row order."""
    from builder import CURRENT_A, PREVIOUS_A, SERIES_A

    a = parse_workbook(workbook_bytes)
    wb_rev = build_workbook(
        current=list(reversed(CURRENT_A)),
        series=list(reversed(SERIES_A)),
        previous=list(reversed(PREVIOUS_A)),
    )
    b = parse_workbook(wb_rev)
    ids_a = {r.disclosure.disclosure_id for r in a.rows}
    ids_b = {r.disclosure.disclosure_id for r in b.rows}
    assert ids_a == ids_b


def test_blank_rows_are_tolerated():
    """Fully blank rows inside a data sheet are skipped, not parsed."""
    from io import BytesIO

    import xlwt
    from builder import CURRENT_A, PREVIOUS_A, SERIES_A, _write_data_sheet

    wb = xlwt.Workbook()
    wb.add_sheet(constants.SHEET_METADATA)
    sh = wb.add_sheet(constants.SHEET_CURRENT)
    for c, h in enumerate(constants.EXPECTED_HEADERS):
        sh.write(3, c, h)
    # data, then a fully blank row, then more data
    for c, v in enumerate(CURRENT_A[0]):
        sh.write(4, c, v)
    for c, v in enumerate(CURRENT_A[1]):
        sh.write(6, c, v)
    _write_data_sheet(wb, constants.SHEET_SERIES, SERIES_A)
    _write_data_sheet(wb, constants.SHEET_PREVIOUS, PREVIOUS_A)
    buf = BytesIO()
    wb.save(buf)
    parsed = parse_workbook(buf.getvalue())
    cur = [r for r in parsed.rows if r.sheet_name == constants.SHEET_CURRENT]
    assert len(cur) == 2
