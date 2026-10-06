"""Expected source schema. Rule-based validation, fails closed.

The fingerprint detects that *something* changed; these rules explain *what*
changed and refuse to parse rather than guess.
"""

from __future__ import annotations

from .. import constants
from ..exceptions import SchemaDriftError
from .inspect import WorkbookInfo


def validate_schema(info: WorkbookInfo) -> None:
    """Raise SchemaDriftError describing the first contract violation."""
    if info.workbook_type != "biff8":
        raise SchemaDriftError(
            f"unsupported workbook type {info.workbook_type!r} (expected 'biff8')"
        )

    names = [s.name for s in info.sheets]
    for required in (
        constants.SHEET_METADATA,
        constants.SHEET_CURRENT,
        constants.SHEET_SERIES,
        constants.SHEET_PREVIOUS,
    ):
        if required not in names:
            raise SchemaDriftError(f"required sheet missing: {required!r}")

    # Data sheets must precede trailing sheets; order of the named sheets is
    # part of the contract.
    positions = [
        names.index(n)
        for n in (
            constants.SHEET_METADATA,
            constants.SHEET_CURRENT,
            constants.SHEET_SERIES,
            constants.SHEET_PREVIOUS,
        )
    ]
    if positions != sorted(positions):
        raise SchemaDriftError(f"named sheets out of expected order: {names}")

    by_name = {s.name: s for s in info.sheets}
    for name in constants.DATA_SHEETS:
        sheet = by_name[name]
        if sheet.ncols != len(constants.EXPECTED_HEADERS):
            raise SchemaDriftError(
                f"sheet {name!r}: expected {len(constants.EXPECTED_HEADERS)} columns, "
                f"found {sheet.ncols}"
            )
        if sheet.headers is None:
            raise SchemaDriftError(
                f"sheet {name!r}: no header row at index " f"{constants.HEADER_ROW_INDEX}"
            )
        if tuple(sheet.headers) != constants.EXPECTED_HEADERS:
            raise SchemaDriftError(
                f"sheet {name!r}: headers changed.\n"
                f"  expected: {list(constants.EXPECTED_HEADERS)}\n"
                f"  found:    {list(sheet.headers)}"
            )
        if sheet.nrows <= constants.HEADER_ROW_INDEX:
            raise SchemaDriftError(f"sheet {name!r}: contains no data rows")

    # Unknown *extra* sheets are only tolerated when completely empty
    # (the workbook currently ships Hoja2..Hoja7 empty).
    for s in info.sheets:
        if s.name not in (constants.SHEET_METADATA, *constants.DATA_SHEETS) and (
            s.nrows != 0 or s.ncols != 0
        ):
            raise SchemaDriftError(
                f"unexpected non-empty sheet {s.name!r} " f"({s.nrows}x{s.ncols})"
            )
