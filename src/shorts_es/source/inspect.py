"""Workbook structure inspection and schema fingerprinting.

The fingerprint covers everything that would change the *meaning* of a parse:
container type, sheet names/order, column count and exact header text. Row
counts are recorded per sheet but are deliberately not part of the
fingerprint because they change with every publication.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import xlrd

from .. import constants
from ..exceptions import UnsupportedWorkbookError


@dataclass(frozen=True)
class SheetInfo:
    name: str
    order: int
    nrows: int
    ncols: int
    headers: tuple[str, ...] | None  # None when sheet has no header row


@dataclass(frozen=True)
class WorkbookInfo:
    workbook_type: str  # "biff8" etc.
    datemode: int
    sheets: tuple[SheetInfo, ...]
    fingerprint: str = field(default="")


def _workbook_type(book: xlrd.Book) -> str:
    # xlrd reports BIFF8 as version 80; normalize to the conventional name.
    return "biff8" if book.biff_version == 80 else f"biff{book.biff_version}"


def compute_fingerprint(workbook_type: str, datemode: int, sheets: tuple[SheetInfo, ...]) -> str:
    """Deterministic sha256 over the workbook's structural contract."""
    payload = {
        "workbook_type": workbook_type,
        "datemode": datemode,
        "sheets": [
            {"name": s.name, "order": s.order, "ncols": s.ncols, "headers": s.headers}
            for s in sheets
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def inspect_workbook(content: bytes) -> WorkbookInfo:
    """Inspect raw workbook bytes. Fails closed on non-OLE2 containers."""
    if not content[:8] == constants.OLE2_MAGIC:
        raise UnsupportedWorkbookError(
            "source is not an OLE2/BIFF workbook (bad magic bytes); "
            "the CNMV format may have changed"
        )
    try:
        book = xlrd.open_workbook(file_contents=content)
    except xlrd.XLRDError as exc:
        raise UnsupportedWorkbookError(f"xlrd cannot open workbook: {exc}") from exc

    sheets: list[SheetInfo] = []
    for order, name in enumerate(book.sheet_names()):
        sh = book.sheet_by_index(order)
        headers = None
        if sh.nrows > constants.HEADER_ROW_INDEX:
            candidate = tuple(
                str(sh.cell(constants.HEADER_ROW_INDEX, c).value).strip() for c in range(sh.ncols)
            )
            if any(candidate):
                headers = candidate
        sheets.append(
            SheetInfo(name=name, order=order, nrows=sh.nrows, ncols=sh.ncols, headers=headers)
        )

    wtype = _workbook_type(book)
    fp = compute_fingerprint(wtype, book.datemode, tuple(sheets))
    return WorkbookInfo(
        workbook_type=wtype, datemode=book.datemode, sheets=tuple(sheets), fingerprint=fp
    )
