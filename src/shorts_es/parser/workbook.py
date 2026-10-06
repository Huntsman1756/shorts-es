"""Deterministic workbook parser.

Same bytes -> same canonical rows -> same disclosure ids. No clocks, no
randomness, no external lookups.
"""

from __future__ import annotations

import re
from datetime import date

import xlrd

from .. import constants
from ..exceptions import ParseError
from ..source.inspect import inspect_workbook
from ..source.schema import validate_schema
from .models import Disclosure, ParsedRow, ParsedWorkbook
from .normalize import norm_date, norm_isin, norm_lei, norm_pct, norm_text

_DATE_IN_TEXT = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _publication_date(book: xlrd.Book) -> date | None:
    """Extract the publication date from the metadata sheet."""
    sh = book.sheet_by_index(0)
    for r in range(sh.nrows):
        for c in range(sh.ncols):
            v = sh.cell(r, c).value
            if isinstance(v, str):
                m = _DATE_IN_TEXT.search(v.strip())
                if m:
                    return date.fromisoformat(m.group(1))
    return None


def _is_empty_row(sh: xlrd.sheet.Sheet, r: int) -> bool:
    return all(
        sh.cell(r, c).ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK)
        or str(sh.cell(r, c).value).strip() == ""
        for c in range(sh.ncols)
    )


def parse_workbook(content: bytes) -> ParsedWorkbook:
    """Parse workbook bytes into canonical rows.

    Fails closed: schema drift, cell-type surprises or invalid values abort
    the whole parse (no partial results).
    """
    info = inspect_workbook(content)
    validate_schema(info)

    book = xlrd.open_workbook(file_contents=content)
    publication_date = _publication_date(book)

    rows: list[ParsedRow] = []
    for name in constants.DATA_SHEETS:
        sh = book.sheet_by_index(book.sheet_names().index(name))
        for r in range(constants.HEADER_ROW_INDEX + 1, sh.nrows):
            if _is_empty_row(sh, r):
                continue  # tolerate blank separator/trailing rows
            if sh.ncols != len(constants.EXPECTED_HEADERS):
                raise ParseError(f"{name} row {r + 1}: unexpected column count")
            values = [sh.cell(r, c).value for c in range(sh.ncols)]
            types = [sh.cell(r, c).ctype for c in range(sh.ncols)]
            for c in range(5):
                if types[c] != xlrd.XL_CELL_TEXT:
                    raise ParseError(
                        f"{name} row {r + 1} col {c}: expected text cell, " f"got ctype {types[c]}"
                    )
            if types[5] != xlrd.XL_CELL_NUMBER:
                raise ParseError(
                    f"{name} row {r + 1}: percentage cell not numeric " f"(ctype {types[5]})"
                )
            try:
                disclosure = Disclosure(
                    lei=norm_lei(values[0]),
                    isin=norm_isin(values[1]),
                    issuer_name=norm_text(values[2], "issuer"),
                    holder_name=norm_text(values[3], "holder"),
                    position_date=norm_date(values[4]),
                    position_pct=norm_pct(values[5]),
                )
            except ParseError as exc:
                raise ParseError(f"{name} row {r + 1}: {exc.message}") from exc
            rows.append(ParsedRow(sheet_name=name, row_number=r + 1, disclosure=disclosure))

    return ParsedWorkbook(publication_date=publication_date, rows=tuple(rows))
