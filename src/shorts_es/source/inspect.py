"""Workbook structure inspection and schema fingerprinting.

Two fingerprints, on purpose:

- ``fingerprint`` (semantic): workbook type, the *named* sheets' names,
  order, column count, exact headers and the percentage-column number
  format contract. A change here can alter the meaning of a parse ->
  SCHEMA_DRIFT / fail closed.
- ``physical_fingerprint``: the full sheet inventory including padding
  sheets (``Hoja2``..``HojaN``) and every column's number formats. Empty
  padding sheets can appear/disappear/rename without semantic impact;
  changes here are recorded for audit, not fatal.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

import xlrd

from .. import constants
from ..exceptions import UnsupportedWorkbookError

PCT_COL = 5
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class SheetInfo:
    name: str
    order: int
    nrows: int
    ncols: int
    headers: tuple[str, ...] | None  # None when sheet has no header row
    pct_formats: tuple[str, ...] = ()  # distinct number formats of col PCT_COL
    is_padding: bool = False  # empty sheet with no semantic role


@dataclass(frozen=True)
class WorkbookInfo:
    workbook_type: str  # "biff8"
    datemode: int
    sheets: tuple[SheetInfo, ...]
    fingerprint: str = field(default="")  # semantic fingerprint
    physical_fingerprint: str = field(default="")


def _workbook_type(book: xlrd.Book) -> str:
    # xlrd reports BIFF8 as version 80; normalize to the conventional name.
    return "biff8" if book.biff_version == 80 else f"biff{book.biff_version}"


def _format_of(book: xlrd.Book, sheet: xlrd.sheet.Sheet, r: int, c: int) -> str:
    cell = sheet.cell(r, c)
    return book.format_map[book.xf_list[cell.xf_index].format_key].format_str


def _semantic_payload(workbook_type: str, datemode: int, sheets: tuple[SheetInfo, ...]) -> dict:
    named = [s for s in sheets if not s.is_padding]
    return {
        "workbook_type": workbook_type,
        "datemode": datemode,
        "sheets": [
            {
                "name": s.name,
                "order": s.order,
                "ncols": s.ncols,
                "headers": s.headers,
                "pct_formats": s.pct_formats,
            }
            for s in named
        ],
    }


def _physical_payload(workbook_type: str, datemode: int, sheets: tuple[SheetInfo, ...]) -> dict:
    return {
        "workbook_type": workbook_type,
        "datemode": datemode,
        "sheets": [
            {
                "name": s.name,
                "order": s.order,
                "nrows": s.nrows,
                "ncols": s.ncols,
                "headers": s.headers,
                "pct_formats": s.pct_formats,
            }
            for s in sheets
        ],
    }


def _sha(payload: dict) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_fingerprint(workbook_type: str, datemode: int, sheets: tuple[SheetInfo, ...]) -> str:
    """Deterministic sha256 over the workbook's *semantic* contract."""
    return _sha(_semantic_payload(workbook_type, datemode, sheets))


def inspect_workbook(content: bytes) -> WorkbookInfo:
    """Inspect raw workbook bytes. Fails closed on non-OLE2 containers."""
    if content[:8] != constants.OLE2_MAGIC:
        raise UnsupportedWorkbookError(
            "source is not an OLE2/BIFF workbook (bad magic bytes); "
            "the CNMV format may have changed"
        )
    try:
        book = xlrd.open_workbook(file_contents=content, formatting_info=True)
    except xlrd.XLRDError as exc:
        raise UnsupportedWorkbookError(f"xlrd cannot open workbook: {exc}") from exc

    sheets: list[SheetInfo] = []
    for order, name in enumerate(book.sheet_names()):
        sh = book.sheet_by_index(order)
        headers = None
        if sh.nrows > constants.HEADER_ROW_INDEX:
            candidate = tuple(
                "<DATE>"
                if _ISO_DATE.match(str(sh.cell(constants.HEADER_ROW_INDEX, c).value).strip())
                else str(sh.cell(constants.HEADER_ROW_INDEX, c).value).strip()
                for c in range(sh.ncols)
            )
            if any(candidate):
                headers = candidate
        pct_formats: tuple[str, ...] = ()
        if sh.ncols > PCT_COL and sh.nrows > constants.HEADER_ROW_INDEX:
            pct_formats = tuple(
                sorted(
                    {
                        _format_of(book, sh, r, PCT_COL)
                        for r in range(constants.HEADER_ROW_INDEX + 1, sh.nrows)
                        if sh.cell(r, PCT_COL).ctype == xlrd.XL_CELL_NUMBER
                    }
                )
            )
        is_padding = sh.nrows == 0
        sheets.append(
            SheetInfo(
                name=name,
                order=order,
                nrows=sh.nrows,
                ncols=sh.ncols,
                headers=headers,
                pct_formats=pct_formats,
                is_padding=is_padding,
            )
        )

    wtype = _workbook_type(book)
    t = tuple(sheets)
    return WorkbookInfo(
        workbook_type=wtype,
        datemode=book.datemode,
        sheets=t,
        fingerprint=_sha(_semantic_payload(wtype, book.datemode, t)),
        physical_fingerprint=_sha(_physical_payload(wtype, book.datemode, t)),
    )
